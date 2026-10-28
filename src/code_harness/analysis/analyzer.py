"""Language-independent execution over a parser's concrete context contract."""

import logging
from dataclasses import dataclass, field

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import Analyzer, ContextParser
from code_harness.analysis.scopes import AffectedScopes, ScopeSyntax
from code_harness.analysis.session import AnalysisSession, SemanticBinding
from code_harness.diagnostics import AnalysisError, Finding, SyntaxFailure
from code_harness.plugins.bundles import BundleRegistry
from code_harness.plugins.profiles import AnalysisProfile
from code_harness.policy.models import Policy
from code_harness.semantics.model import SemanticSyntax
from code_harness.source import LanguageDefinition, Source
from code_harness.suppressions import CommentSuppressions, DirectiveSyntax, ParsedSuppressions


@dataclass(frozen=True, slots=True)
class TypedAnalyzer(Analyzer):
    """Compose one context parser and its compatible registered rule objects."""

    name: str = field()
    definition: LanguageDefinition = field()
    parser: ContextParser
    bundles: BundleRegistry
    profile: AnalysisProfile = field()
    semantics: SemanticSyntax | None = None
    api_version: int = 2
    scopes: ScopeSyntax | None = None
    directives: DirectiveSyntax | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate late bundle additions independently of checker enable flags."""
        self.profile.validate(self.rule_ids)
        if self.bundles.requires_semantics and self.semantics is None:
            raise AnalysisError("Required semantic capability is unavailable")

    def needs_semantics(self, policy: Policy) -> bool:
        """Select evidence work using enabled consumer requirements."""
        return self.bundles.needs_semantics(policy.checkers.disabled_rules())

    @property
    def semantic_binding(self) -> SemanticBinding | None:
        if self.semantics is None:
            return None
        return SemanticBinding(self.parser, self.semantics)

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return self.bundles.rule_ids

    def analyze(
        self, source: Source, policy: Policy, session: AnalysisSession | None = None
    ) -> tuple[Finding, ...]:
        self.validate()
        if session is not None and session.policy != policy:
            raise AnalysisError("Analysis session policy does not match this execution")
        if source.language != self.definition.language:
            raise AnalysisError(f"{self.name} cannot analyze {source.language}")
        if self.profile.optional_unavailable:
            logging.getLogger(__name__).warning(
                "Optional analyses unavailable for %r: %s",
                source.path,
                ", ".join(self.profile.optional_unavailable),
            )
        disabled = policy.checkers.disabled_rules()
        if all(rule in disabled for rule in self.rule_ids):
            return ()
        try:
            context = self._context(source, policy, session)
        except SyntaxFailure:
            return ()
        return self._findings(context, disabled)

    def _findings(self, context: TreeContext, disabled: frozenset[str]) -> tuple[Finding, ...]:
        findings = self.bundles.run(context, disabled)
        suppressions = (
            CommentSuppressions(self.directives, self.rule_ids).parse(context)
            if self.directives is not None
            else ParsedSuppressions()
        )
        lines: frozenset[int] | None = None
        if context.source.changed_lines is not None:
            if self.scopes is None:
                raise AnalysisError(f"Affected-scope capability unavailable for {self.name}")
            scopes = AffectedScopes(self.scopes)
            lines = scopes.lines(context, suppressions.target_lines(context.source.changed_lines))
            findings = tuple(finding for finding in findings if scopes.includes(finding, lines))
        findings = suppressions.apply(findings, lines)
        return tuple(
            sorted(
                (finding for finding in findings if finding.rule not in disabled), key=_finding_key
            )
        )

    def _context(
        self, source: Source, policy: Policy, session: AnalysisSession | None
    ) -> TreeContext:
        active = session or AnalysisSession(policy)
        if session is None and self.semantics is not None and self.needs_semantics(policy):
            active.prepare(
                (source,), {source.language: SemanticBinding(self.parser, self.semantics)}
            )
        return active.context(source, self.parser)


def _finding_key(finding: Finding) -> tuple[str, int, int, str, str]:
    return finding.path, finding.line, finding.column, finding.rule, finding.message


__all__ = ["SyntaxFailure", "TypedAnalyzer"]
