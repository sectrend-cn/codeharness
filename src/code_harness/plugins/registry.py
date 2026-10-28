"""Validated analyzer registration and source-discovery ownership."""

from code_harness.analysis.contracts import Analyzer
from code_harness.analysis.session import AnalysisSession, SemanticBinding
from code_harness.diagnostics import AnalysisError, Finding
from code_harness.plugins.languages import LanguageRegistry
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


class AnalyzerRegistry:
    """Own unique language identities, suffixes, and mandatory rule coverage."""

    def __init__(self) -> None:
        self._names: set[str] = set()
        self._analyzers: dict[Language, Analyzer] = {}
        self._languages = LanguageRegistry()
        self._semantics: dict[Language, SemanticBinding] = {}

    def register(self, analyzer: Analyzer) -> None:
        """Validate a whole registration before publishing any of its state."""
        self._validate(analyzer)
        definition = analyzer.definition
        self._languages.register(definition)
        self._names.add(analyzer.name)
        self._analyzers[definition.language] = analyzer
        if analyzer.semantic_binding is not None:
            self._semantics[definition.language] = analyzer.semantic_binding

    def _validate(self, analyzer: Analyzer) -> None:
        if not analyzer.name or analyzer.name in self._names:
            raise AnalysisError(f"Duplicate or empty analyzer identity: {analyzer.name!r}")
        if analyzer.api_version != 2:
            raise AnalysisError(f"Unsupported analyzer API version: {analyzer.api_version}")
        self._languages.validate(analyzer.definition)
        self._validate_rules(analyzer)
        analyzer.validate()

    def _validate_rules(self, analyzer: Analyzer) -> None:
        rules = analyzer.rule_ids
        if not rules or len(set(rules)) != len(rules) or any(not rule for rule in rules):
            raise AnalysisError(f"Invalid rule declarations for analyzer: {analyzer.name}")
        analyzer.profile.validate(rules)

    def language_for(self, path: str) -> Language | None:
        """Discover sources using the same registrations that execute checks."""
        return self._languages.language_for(path)

    def analyze(
        self, source: Source, policy: Policy, session: AnalysisSession | None = None
    ) -> tuple[Finding, ...]:
        """Run the required analyzer and fail closed if it is absent or broken."""
        analyzer = self._analyzers.get(source.language)
        if analyzer is None:
            raise AnalysisError(f"No required analyzer registered for {source.language}")
        analyzer.validate()
        disabled = policy.checkers.disabled_rules()
        if all(rule in disabled for rule in analyzer.rule_ids):
            return ()
        try:
            findings = analyzer.analyze(source, policy, session)
            if any(finding.rule not in analyzer.rule_ids for finding in findings):
                raise AnalysisError(f"Analyzer {analyzer.name} emitted an undeclared rule")
            return tuple(finding for finding in findings if finding.rule not in disabled)
        except AnalysisError:
            raise
        except Exception as error:
            raise AnalysisError(f"Analyzer {analyzer.name} failed: {error}") from error

    def analyze_sources(
        self, sources: tuple[Source, ...], policy: Policy, references: tuple[Source, ...] = ()
    ) -> tuple[Finding, ...]:
        """Prepare project evidence before local rules consume shared contexts."""
        for analyzer in self._analyzers.values():
            analyzer.validate()
        session = AnalysisSession(policy)
        needs_semantics = any(
            self._analyzers[source.language].needs_semantics(policy)
            for source in sources
            if source.language in self._analyzers
        )
        bindings = self._semantics if needs_semantics else {}
        snapshots = self._snapshots(sources, references, bindings)
        session.prepare(snapshots, bindings)
        return tuple(f for source in sources for f in self.analyze(source, policy, session))

    def _snapshots(
        self,
        sources: tuple[Source, ...],
        references: tuple[Source, ...],
        bindings: dict[Language, SemanticBinding],
    ) -> tuple[Source, ...]:
        selected = {(source.language, source.path) for source in sources}
        peers = tuple(
            source for source in references if (source.language, source.path) not in selected
        )
        unique = tuple(dict.fromkeys((*sources, *peers)))
        seen: dict[tuple[Language, str], Source] = {}
        for source in unique:
            key = source.language, source.path
            if key in seen and seen[key] != source and source.language in bindings:
                raise AnalysisError(f"Conflicting semantic snapshots for {source.path}")
            seen[key] = source
        return unique
