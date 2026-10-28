"""Exercise fail-closed analyzer registration with concrete contracts."""

from dataclasses import dataclass

import pytest

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import Analyzer
from code_harness.analysis.requirements import RuleRequirements
from code_harness.analysis.session import AnalysisSession, SemanticBinding
from code_harness.diagnostics import AnalysisError, Finding
from code_harness.languages.python import PythonLanguage
from code_harness.plugins.bundles import BundleRegistry
from code_harness.plugins.profiles import AnalysisProfile
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.policy.models import Policy
from code_harness.source import Language, LanguageDefinition, Source
from code_harness.syntax import parse as parse_tree


@dataclass(frozen=True)
class _FailingAnalyzer(Analyzer):
    """A registered analyzer that fails during execution."""

    name: str = "test.failing"
    definition: LanguageDefinition = PythonLanguage().definition
    profile: AnalysisProfile = AnalysisProfile(("type.signature", "type.broad"))
    semantic_binding: SemanticBinding | None = None
    api_version: int = 2
    rule_ids: tuple[str, ...] = (
        "type.suppression",
        "size.lines",
        "size.statements",
        "size.complexity",
        "size.nesting",
        "size.parameters",
        "architecture.owner",
        "architecture.structure",
        "architecture.import",
        "architecture.dispatch",
        "architecture.object_model",
        "type.annotation",
        "type.signature",
        "type.assertion",
        "type.broad",
        "imports.wildcard",
        "type.boundary",
        "unused.parameter",
        "unused.function",
        "unused.field",
        "unused.return",
        "test.failure",
    )

    def needs_semantics(self, policy: Policy) -> bool:
        """The synthetic failing analyzer has no semantic evidence consumer."""
        return False

    def validate(self) -> None:
        """This synthetic failing analyzer requires no syntax capabilities."""

    def analyze(
        self, source: Source, policy: Policy, session: AnalysisSession | None = None
    ) -> tuple[Finding, ...]:
        """Accept Analyzer inputs and fail before applying policy."""
        raise RuntimeError("fixture failure")


def test_missing_required_analyzer_fails_closed() -> None:
    registry = AnalyzerRegistry()
    source = Source("app.py", b"", Language.PYTHON)

    with pytest.raises(AnalysisError, match="No required analyzer"):
        registry.analyze(source, Policy())


def test_duplicate_language_registration_fails_closed() -> None:
    registry = AnalyzerRegistry()
    analyzer = _FailingAnalyzer()
    registry.register(analyzer)

    with pytest.raises(AnalysisError, match="Duplicate analyzer for language"):
        registry.register(_FailingAnalyzer(name="test.second"))


def test_analyzer_failure_fails_closed() -> None:
    registry = AnalyzerRegistry()
    analyzer = _FailingAnalyzer()
    registry.register(analyzer)

    with pytest.raises(AnalysisError, match="Analyzer test.failing failed"):
        registry.analyze(Source("app.py", b"", Language.PYTHON), Policy())


@dataclass(frozen=True)
class _FailingTreeBundle:
    """A typed bundle that fails during execution."""

    name: str = "test.bundle"
    requirements: RuleRequirements = RuleRequirements()
    api_version: int = 2
    rule_ids: tuple[str, ...] = ("test.bundle.rule",)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        raise RuntimeError("bundle fixture failure")


def test_analyzer_missing_required_rule_fails_closed() -> None:
    registry = AnalyzerRegistry()
    analyzer = _FailingAnalyzer(rule_ids=("type.broad",))

    with pytest.raises(AnalysisError, match="missing rules"):
        registry.register(analyzer)


def test_duplicate_rule_ownership_fails_closed() -> None:
    registry = BundleRegistry()
    registry.register(_FailingTreeBundle())

    with pytest.raises(AnalysisError, match="Conflicting rule ownership"):
        registry.register(_FailingTreeBundle(name="test.second"))


def test_bundle_failure_fails_closed() -> None:
    registry = BundleRegistry()
    registry.register(_FailingTreeBundle())
    source = Source("app.js", b"const value = 1;", Language.JAVASCRIPT)
    context = TreeContext(source, parse_tree(source), Policy())

    with pytest.raises(AnalysisError, match="Rule bundle test.bundle failed"):
        registry.run(context)


@pytest.mark.parametrize(
    "analyzer",
    [
        _FailingAnalyzer(name=""),
        _FailingAnalyzer(api_version=1),
        _FailingAnalyzer(rule_ids=()),
        _FailingAnalyzer(rule_ids=("type.broad", "type.broad")),
        _FailingAnalyzer(rule_ids=("type.broad", "")),
    ],
)
def test_invalid_analyzer_metadata_fails_closed(analyzer: _FailingAnalyzer) -> None:
    with pytest.raises(AnalysisError):
        AnalyzerRegistry().register(analyzer)


@pytest.mark.parametrize(
    "suffixes", [(), (".py", ".py"), ("py",), (".",), (".bad/path",), (".foo.bar",)]
)
def test_invalid_suffixes_cannot_hide_selected_files(suffixes: tuple[str, ...]) -> None:
    definition = LanguageDefinition(Language.PYTHON, suffixes)
    with pytest.raises(AnalysisError, match="suffix"):
        AnalyzerRegistry().register(_FailingAnalyzer(definition=definition))


def test_conflicting_suffix_registration_is_atomic() -> None:
    registry = AnalyzerRegistry()
    registry.register(_FailingAnalyzer())
    language = Language("alternative")
    conflicting = LanguageDefinition(language, (".new", ".py"))
    with pytest.raises(AnalysisError, match="Conflicting language suffix"):
        registry.register(_FailingAnalyzer(name="test.alternative", definition=conflicting))
    assert registry.language_for("example.new") is None
    assert registry.language_for("example.py") == Language.PYTHON
    accepted = LanguageDefinition(language, (".new",))
    registry.register(_FailingAnalyzer(name="test.alternative", definition=accepted))
    assert registry.language_for("example.new") == language


@pytest.mark.parametrize("required", [(), ("",), ("type.broad", "type.broad")])
def test_invalid_required_rules_are_rejected(required: tuple[str, ...]) -> None:
    with pytest.raises(AnalysisError, match="Invalid required rules"):
        AnalyzerRegistry().register(_FailingAnalyzer(profile=AnalysisProfile(required)))


@pytest.mark.parametrize(
    "bundle",
    [
        _FailingTreeBundle(name=""),
        _FailingTreeBundle(api_version=1),
        _FailingTreeBundle(rule_ids=()),
        _FailingTreeBundle(rule_ids=("test.rule", "test.rule")),
        _FailingTreeBundle(rule_ids=("",)),
    ],
)
def test_invalid_bundle_metadata_fails_closed(bundle: _FailingTreeBundle) -> None:
    with pytest.raises(AnalysisError):
        BundleRegistry().register(bundle)


class _UndeclaredBundle(_FailingTreeBundle):
    """Exercise the rule-ownership check after an otherwise valid registration."""

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        return (
            Finding(
                path=context.source.path,
                line=1,
                column=1,
                rule="unregistered",
                message="Invalid plugin output",
            ),
        )


def test_undeclared_bundle_findings_fail_closed() -> None:
    registry = BundleRegistry()
    registry.register(_UndeclaredBundle())
    source = Source("app.js", b"", Language.JAVASCRIPT)
    with pytest.raises(AnalysisError, match="undeclared rule"):
        registry.run(TreeContext(source, parse_tree(source), Policy()))


class _UndeclaredAnalyzer(_FailingAnalyzer):
    """Exercise analyzer-level output validation independently of bundle machinery."""

    def analyze(
        self, source: Source, policy: Policy, session: AnalysisSession | None = None
    ) -> tuple[Finding, ...]:
        """Accept Analyzer inputs and emit an ownership violation regardless of policy."""
        return (
            Finding(
                path=source.path,
                line=1,
                column=1,
                rule="unregistered",
                message="Invalid analyzer output",
            ),
        )


def test_undeclared_analyzer_findings_fail_closed() -> None:
    registry = AnalyzerRegistry()
    registry.register(_UndeclaredAnalyzer())
    with pytest.raises(AnalysisError, match="undeclared rule"):
        registry.analyze(Source("app.py", b"", Language.PYTHON), Policy())


def test_duplicate_bundle_identity_is_rejected() -> None:
    registry = BundleRegistry()
    bundle = _FailingTreeBundle()
    registry.register(bundle)
    with pytest.raises(AnalysisError, match="Duplicate or empty rule bundle"):
        registry.register(bundle)


def test_duplicate_analyzer_identity_is_rejected() -> None:
    registry = AnalyzerRegistry()
    analyzer = _FailingAnalyzer()
    registry.register(analyzer)
    with pytest.raises(AnalysisError, match="Duplicate or empty analyzer"):
        registry.register(analyzer)


def test_fully_disabled_bundle_is_not_invoked() -> None:
    registry = BundleRegistry()
    registry.register(_FailingTreeBundle())
    source = Source("app.js", b"", Language.JAVASCRIPT)
    context = TreeContext(source, parse_tree(source), Policy())
    assert registry.run(context, frozenset({"test.bundle.rule"})) == ()


def test_disabled_findings_do_not_hide_invalid_bundle_output() -> None:
    registry = BundleRegistry()
    registry.register(_UndeclaredBundle(rule_ids=("test.first", "test.second")))
    source = Source("app.js", b"", Language.JAVASCRIPT)
    context = TreeContext(source, parse_tree(source), Policy())
    with pytest.raises(AnalysisError, match="undeclared rule"):
        registry.run(context, frozenset({"test.first", "unregistered"}))
