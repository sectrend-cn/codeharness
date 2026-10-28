"""Exercise independently registered languages and rules through the production CLI."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tree_sitter import Node

from code_harness.analysis.analyzer import SyntaxFailure, TypedAnalyzer
from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import ContextParser
from code_harness.analysis.requirements import RuleRequirements
from code_harness.analysis.session import AnalysisSession
from code_harness.cli import main
from code_harness.diagnostics import AnalysisError, Finding, ParseWarning
from code_harness.languages.python import PythonLanguage
from code_harness.languages.python.semantic_syntax import PythonSemanticSyntax
from code_harness.languages.python.syntax import PythonSuppressions
from code_harness.parsing.treesitter import TreeParser
from code_harness.plugins.builtins import builtin_analyzers
from code_harness.plugins.bundles import BundleRegistry
from code_harness.plugins.profiles import AnalysisProfile
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.policy.models import (
    BroadTypeOptions,
    Checkers,
    FunctionSizeOptions,
    Policy,
)
from code_harness.snapshots import Selection, sources
from code_harness.source import Language, LanguageDefinition, Source
from code_harness.suppressions import SuppressionRule

_COUNTER = Language("counter")


def _count_node(context: TreeContext) -> Node | None:
    """Recognize the count dialect through concrete tree-sitter evidence."""
    statements = context.root.named_children
    if context.root.has_error or len(statements) != 1:
        return None
    expression = statements[0]
    if expression.type != "expression_statement" or expression.named_child_count != 1:
        return None
    assignment = expression.named_children[0]
    if assignment.type != "assignment":
        return None
    name = assignment.child_by_field_name("left")
    value = assignment.child_by_field_name("right")
    if name is None or name.text != b"count" or value is None or value.type != "integer":
        return None
    return value


@dataclass
class CounterParser(ContextParser):
    """A Python-grammar dialect exercises independently registered tree parsing."""

    calls: int = 0
    syntax: TreeParser = field(default_factory=lambda: PythonLanguage().parser)

    def parse(self, source: Source, policy: Policy) -> TreeContext:
        self.calls += 1
        context = self.syntax.parse(source, policy)
        if _count_node(context) is None:
            raise SyntaxFailure(
                (
                    ParseWarning(
                        path=source.path,
                        line=1,
                        column=1,
                        message="Expected count = INTEGER; dependent checks skipped",
                    ),
                )
            )
        return context


@dataclass
class CounterRule:
    """Consume the plugin's exact domain context and own its declared diagnostic."""

    name: str = "counter.limit"
    requirements: RuleRequirements = RuleRequirements()
    api_version: int = 2
    rule_ids: tuple[str, ...] = ("counter.limit",)
    calls: int = 0
    maximum: int = 3

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        self.calls += 1
        node = _count_node(context)
        if node is None or node.text is None:
            raise AnalysisError("Counter rule requires count syntax evidence")
        count = int(node.text, 0)
        if count <= self.maximum:
            return ()
        return (
            Finding(
                path=context.source.path,
                line=1,
                column=9,
                rule=self.rule_ids[0],
                message=f"Count {count} exceeds {self.maximum}",
            ),
        )


def _counter_analyzer() -> TypedAnalyzer:
    bundles = BundleRegistry()
    bundles.register(CounterRule())
    definition = LanguageDefinition(_COUNTER, (".count",))
    return TypedAnalyzer(
        "counter", definition, CounterParser(), bundles, AnalysisProfile(("counter.limit",))
    )


def test_new_language_runs_through_cli_and_discovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registry = AnalyzerRegistry()
    registry.register(_counter_analyzer())
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text('{"version": 2}')
    path = tmp_path / "example.count"
    path.write_text("count = 7")
    assert main(["--root", str(tmp_path), "--all"], registry) == 1
    assert "example.count:1:9: counter.limit: Count 7 exceeds 3" in capsys.readouterr().out
    inputs = sources(Selection(tmp_path, "all"), Policy(), registry)
    assert inputs == (Source("example.count", b"count = 7", _COUNTER),)
    path.write_text("count = 2")
    assert main(["--root", str(tmp_path), "--all"], registry) == 0


@pytest.mark.parametrize("content", [b"", b"count", b"count wrong", b"other 5"])
def test_custom_syntax_failure_warns_and_skips_unavailable_context(
    content: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    parser = CounterParser()
    rule = CounterRule()
    bundles = BundleRegistry()
    bundles.register(rule)
    analyzer = TypedAnalyzer(
        "counter",
        _counter_analyzer().definition,
        parser,
        bundles,
        AnalysisProfile(("counter.limit",)),
    )
    findings = analyzer.analyze(Source("example.count", content, _COUNTER), Policy())
    assert findings == ()
    assert "Expected count = INTEGER; dependent checks skipped" in caplog.text
    assert "analysis results may be inaccurate" in caplog.text
    assert parser.calls == 1
    assert rule.calls == 0


def test_custom_context_is_parsed_once_for_all_rules() -> None:
    parser = CounterParser()
    rule = CounterRule()
    bundles = BundleRegistry()
    bundles.register(rule)
    extra = CounterRule(name="counter.additional", rule_ids=("counter.additional",), maximum=10)
    bundles.register(extra)
    analyzer = TypedAnalyzer(
        "counter",
        _counter_analyzer().definition,
        parser,
        bundles,
        AnalysisProfile(("counter.limit",)),
    )
    assert analyzer.analyze(Source("example.count", b"count = 1", _COUNTER), Policy()) == ()
    assert parser.calls == rule.calls == extra.calls == 1


@dataclass(frozen=True)
class TreeModuleRule:
    """One rule reads the common tree context without language identity checks."""

    name: str = "test.python.module"
    requirements: RuleRequirements = RuleRequirements()
    api_version: int = 2
    rule_ids: tuple[str, ...] = ("test.python.module",)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        return (
            Finding(
                path=context.source.path,
                line=1,
                column=1,
                rule="test.python.module",
                message=f"Module has {context.root.named_child_count} statements",
            ),
        )


def _python_analyzer() -> TypedAnalyzer:
    analyzers = {analyzer.definition.language: analyzer for analyzer in builtin_analyzers()}
    return analyzers[Language.PYTHON]


def test_new_rule_extends_builtin_without_engine_dispatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    analyzer = _python_analyzer()
    analyzer.bundles.register(TreeModuleRule())
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text('{"version": 2}')
    (tmp_path / "app.py").write_text("value: int = 1\n")
    assert main(["--root", str(tmp_path), "--all"], registry) == 1
    assert "test.python.module: Module has 1 statements" in capsys.readouterr().out


def test_typed_analyzer_rejects_wrong_language() -> None:
    with pytest.raises(AnalysisError, match="cannot analyze"):
        _counter_analyzer().analyze(Source("app.py", b"count = 1", Language.PYTHON), Policy())


def test_syntax_failure_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        raise SyntaxFailure(())


def test_custom_language_staged_selection_preserves_snapshots(tmp_path: Path) -> None:
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    source = tmp_path / "example.count"
    source.write_text("count = 9")
    subprocess.run(("git", "-C", str(tmp_path), "add", "example.count"), check=True)
    source.write_text("count = 1")
    registry = AnalyzerRegistry()
    registry.register(_counter_analyzer())
    inputs = sources(Selection(tmp_path, "staged"), Policy(), registry)
    assert inputs == (Source("example.count", b"count = 9", _COUNTER),)
    assert registry.analyze(inputs[0], Policy())[0].rule == "counter.limit"
    assert source.read_text() == "count = 1"


class BrokenCounterParser(ContextParser):
    """A parser infrastructure failure must reach the CLI as a tool error."""

    def parse(self, source: Source, policy: Policy) -> TreeContext:
        """Accept ContextParser inputs and fail before processing source or policy."""
        raise RuntimeError("parser unavailable")


def test_plugin_failure_reaches_cli_as_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _counter_analyzer()
    analyzer = TypedAnalyzer(
        "counter", original.definition, BrokenCounterParser(), original.bundles, original.profile
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text('{"version": 2}')
    (tmp_path / "example.count").write_text("count = 2")
    assert main(["--root", str(tmp_path), "--all"], registry) == 2
    assert "parser unavailable" in capsys.readouterr().err


def test_python_type_comments_use_tree_sitter_without_ast_rejection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = Source("app.py", b"value: int = 1 # type: int\n# type: ignore\n", Language.PYTHON)
    findings = _python_analyzer().analyze(source, Policy())
    assert [finding.rule for finding in findings] == ["type.suppression"]
    assert findings[0].line == 2
    assert "syntax warning" not in caplog.text


def test_findings_are_sorted_independently_of_registration_order() -> None:
    analyzer = _counter_analyzer()
    analyzer.bundles.register(
        CounterRule(name="counter.additional", rule_ids=("counter.additional",), maximum=4)
    )
    findings = analyzer.analyze(Source("example.count", b"count = 8", _COUNTER), Policy())
    assert [finding.rule for finding in findings] == ["counter.additional", "counter.limit"]


@pytest.mark.parametrize("identity", ["", "not valid", "python/path"])
def test_language_identity_rejects_invalid_names(identity: str) -> None:
    with pytest.raises(ValueError, match="identities"):
        Language(identity)


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, b"value: int = 1\n"),
        (Language.JAVASCRIPT, b"const value = 1;"),
        (Language.TYPESCRIPT, b"const value: number = 1;"),
        (Language.TSX, b"const value = <div/>;"),
        (Language.GO, b"package demo\n"),
    ],
)
def test_one_rule_consumes_the_same_context_across_grammars(
    language: Language, code: bytes
) -> None:
    analyzer = next(a for a in builtin_analyzers() if a.definition.language == language)
    context = analyzer.parser.parse(Source("sample", code, language), Policy())
    bundles = BundleRegistry()
    bundles.register(TreeModuleRule())
    findings = bundles.run(context)
    assert len(findings) == 1
    assert findings[0].message == "Module has 1 statements"
    assert context.root == context.tree.root_node


def test_session_reuses_duplicate_snapshots_without_reusing_later_runs() -> None:
    analyzer = _counter_analyzer()
    parser = CounterParser()
    analyzer = TypedAnalyzer(
        analyzer.name, analyzer.definition, parser, analyzer.bundles, analyzer.profile
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    source = Source("example.count", b"count = 7", _COUNTER)
    assert len(registry.analyze_sources((source, source), Policy())) == 2
    assert parser.calls == 1
    assert len(registry.analyze_sources((source,), Policy())) == 1
    assert parser.calls == 2


def test_session_distinguishes_exact_contents_at_the_same_path() -> None:
    original = _counter_analyzer()
    parser = CounterParser()
    analyzer = TypedAnalyzer(
        original.name, original.definition, parser, original.bundles, original.profile
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    passing = Source("example.count", b"count = 2", _COUNTER)
    failing = Source("example.count", b"count = 7", _COUNTER)
    findings = registry.analyze_sources((passing, failing), Policy())
    assert parser.calls == 2
    assert len(findings) == 1
    assert findings[0].message == "Count 7 exceeds 3"


def test_late_semantic_requirement_fails_registration_and_execution() -> None:
    original = _counter_analyzer()
    parser = CounterParser()
    analyzer = TypedAnalyzer(
        original.name, original.definition, parser, original.bundles, original.profile
    )
    analyzer.bundles.register(
        CounterRule(
            name="counter.semantic",
            rule_ids=("size.lines",),
            requirements=RuleRequirements(semantic_evidence=True),
        )
    )
    with pytest.raises(AnalysisError, match="[Ss]emantic"):
        AnalyzerRegistry().register(analyzer)
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(enabled=False)))
    with pytest.raises(AnalysisError, match="[Ss]emantic"):
        assert analyzer.analyze(Source("example.count", b"count = 1", _COUNTER), policy) == ()
    assert parser.calls == 0


def test_optional_unavailable_analysis_is_disclosed(caplog: pytest.LogCaptureFixture) -> None:
    original = _counter_analyzer()
    analyzer = TypedAnalyzer(
        original.name,
        original.definition,
        original.parser,
        original.bundles,
        AnalysisProfile(("counter.limit",), optional_unavailable=("counter.optional",)),
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    assert registry.analyze(Source("example.count", b"count = 1", _COUNTER), Policy()) == ()
    assert "counter.optional" in caplog.text
    assert "unavailable" in caplog.text.lower()


def test_profile_cannot_label_an_available_rule_unavailable() -> None:
    original = _counter_analyzer()
    with pytest.raises(AnalysisError, match="[Aa]vailable"):
        TypedAnalyzer(
            original.name,
            original.definition,
            original.parser,
            original.bundles,
            AnalysisProfile(("counter.limit",), optional_unavailable=("counter.limit",)),
        )


class _BrokenSemanticSyntax(PythonSemanticSyntax):
    """Fail inside semantic preparation after a successful tree parse."""

    def parameters(self, node: Node) -> tuple[Node, ...]:
        """Keep the syntax contract while simulating unavailable interpretation."""
        raise RuntimeError("semantic fixture unavailable")


def test_semantic_preparation_failure_reaches_cli_as_tool_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = _python_analyzer()
    analyzer = TypedAnalyzer(
        original.name,
        original.definition,
        original.parser,
        original.bundles,
        original.profile,
        _BrokenSemanticSyntax(),
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text('{"version": 2}')
    (tmp_path / "app.py").write_text("def run(value: int) -> int:\n    return value\n")
    assert main(["--root", str(tmp_path), "--all"], registry) == 2
    assert "semantic fixture unavailable" in capsys.readouterr().err


def test_analyzer_rejects_session_from_a_different_policy() -> None:
    session = AnalysisSession(Policy(third_party_modules=("vendor",)))
    with pytest.raises(AnalysisError, match="[Pp]olicy"):
        assert (
            _counter_analyzer().analyze(
                Source("example.count", b"count = 1", _COUNTER), Policy(), session
            )
            == ()
        )


def test_session_caches_syntax_rejection_and_emits_its_warning_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    original = _counter_analyzer()
    parser = CounterParser()
    analyzer = TypedAnalyzer(
        original.name, original.definition, parser, original.bundles, original.profile
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    source = Source("example.count", b"other = 1", _COUNTER)
    assert registry.analyze_sources((source, source), Policy()) == ()
    assert parser.calls == 1
    assert caplog.text.count("Expected count = INTEGER") == 1


def _tree_only_analyzer(bundles: BundleRegistry) -> TypedAnalyzer:
    plugin = PythonLanguage()
    return TypedAnalyzer(
        "test.tree_only",
        plugin.definition,
        plugin.parser,
        bundles,
        AnalysisProfile(bundles.rule_ids),
        _BrokenSemanticSyntax(),
    )


@pytest.mark.parametrize("project", [False, True])
def test_tree_only_rules_do_not_prepare_unused_semantic_capabilities(project: bool) -> None:
    bundles = BundleRegistry()
    bundles.register(TreeModuleRule())
    registry = AnalyzerRegistry()
    registry.register(_tree_only_analyzer(bundles))
    source = Source("app.py", b"def run() -> None:\n    pass\n", Language.PYTHON)
    findings = (
        registry.analyze_sources((source,), Policy())
        if project
        else registry.analyze(source, Policy())
    )
    assert len(findings) == 1
    assert findings[0].rule == "test.python.module"


def test_disabled_semantic_bundle_does_not_prepare_its_evidence() -> None:
    bundles = BundleRegistry()
    bundles.register(TreeModuleRule())
    bundles.register(
        CounterRule(
            name="test.disabled_semantic",
            rule_ids=("type.broad",),
            requirements=RuleRequirements(semantic_evidence=True),
        )
    )
    registry = AnalyzerRegistry()
    registry.register(_tree_only_analyzer(bundles))
    source = Source("app.py", b"def run() -> None:\n    pass\n", Language.PYTHON)
    policy = Policy(checkers=Checkers(type_broad=BroadTypeOptions(enabled=False)))
    findings = registry.analyze_sources((source,), policy)
    assert len(findings) == 1
    assert findings[0].rule == "test.python.module"


@pytest.mark.parametrize("project", [False, True])
def test_semantic_capability_does_not_enable_unregistered_usage_rules(project: bool) -> None:
    plugin = PythonLanguage()
    bundles = BundleRegistry()
    bundles.register(SuppressionRule(PythonSuppressions()))
    analyzer = TypedAnalyzer(
        "test.suppression_only",
        plugin.definition,
        plugin.parser,
        bundles,
        AnalysisProfile(("type.suppression",)),
        PythonSemanticSyntax(),
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    source = Source(
        "example.py", b"def _unused(value: int) -> int:\n    return 1\n", Language.PYTHON
    )
    findings = (
        registry.analyze_sources((source,), Policy())
        if project
        else registry.analyze(source, Policy())
    )
    assert findings == ()


def test_changed_source_requires_custom_scope_capability() -> None:
    source = Source("example.count", b"count = 9", _COUNTER, changed_lines=frozenset({1}))
    with pytest.raises(AnalysisError, match="Affected-scope capability unavailable"):
        _counter_analyzer().analyze(source, Policy())
