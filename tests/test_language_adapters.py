"""Exercise independent grammar registration and snapshot compatibility boundaries."""

import pytest

from code_harness.analysis.analyzer import TypedAnalyzer
from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import ContextParser
from code_harness.diagnostics import AnalysisError, ParseWarning, SyntaxFailure
from code_harness.engine import check
from code_harness.imports import PythonImports, RelativeImportResolver, TreeImports
from code_harness.languages.javascript.plugin import JavaScriptLanguage
from code_harness.languages.python.semantic_syntax import PythonSemanticSyntax
from code_harness.plugins.builtins import builtin_registry, tree_parser
from code_harness.plugins.bundles import BundleRegistry
from code_harness.plugins.languages import LanguageRegistry
from code_harness.plugins.profiles import AnalysisProfile
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.policy.models import Boundary, Checkers, ImportOptions, Policy
from code_harness.semantics.boundaries import BoundaryRule
from code_harness.source import Language, LanguageDefinition, Source


def test_language_discovery_registers_without_any_rules() -> None:
    registry = LanguageRegistry()
    language = Language("independent")
    registry.register(LanguageDefinition(language, (".example",)))
    assert registry.language_for("nested/source.example") == language
    with pytest.raises(AnalysisError, match="Conflicting language suffix"):
        registry.register(LanguageDefinition(Language("ambiguous"), (".new", ".example")))
    assert registry.language_for("source.new") is None


@pytest.mark.parametrize(
    ("language", "content", "expected"),
    [
        (Language.GO, b'package p\nimport "vendor"', ("vendor",)),
        (Language.JAVASCRIPT, b'import value from "vendor";', ("vendor",)),
        (Language.TYPESCRIPT, b'import value = require("vendor");', ("vendor",)),
        (Language.JAVASCRIPT, b'const value = require("vendor");', ("vendor",)),
        (Language.JAVASCRIPT, b"const value = require(name);", ()),
        (Language.JAVASCRIPT, b'const value = require("one", "two");', ()),
        (Language.JAVASCRIPT, b'import value from "ven\\x64or";', ()),
    ],
)
def test_compatibility_dependency_facade_retains_literal_semantics(
    language: Language, content: bytes, expected: tuple[str, ...]
) -> None:
    source = Source("sample", content, language)
    context = TreeContext(source, tree_parser(language).tree(source), Policy())
    assert tuple(item.module for item in TreeImports().extract(context)) == expected


def test_python_import_facade_preserves_module_and_member_evidence() -> None:
    source = Source("pkg/source.py", b"from .model import Entity as Alias\n", Language.PYTHON)
    context = TreeContext(source, tree_parser(source.language).tree(source), Policy())
    assert tuple(item.module for item in PythonImports().extract(context)) == (
        "pkg.model",
        "pkg.model.Entity",
    )


def test_relative_resolver_facade_preserves_normalized_source_identity() -> None:
    source = Source("pkg/source.js", b'import value from "./model.js";', Language.JAVASCRIPT)
    context = JavaScriptLanguage().parser.parse(source, Policy())
    dependency = TreeImports().extract(context)[0]
    assert RelativeImportResolver().names(dependency, source) == (
        "./model.js",
        "pkg/model.js",
        "pkg/model",
    )


def test_typescript_import_require_uses_shared_architecture_policy() -> None:
    source = Source("app.ts", b'import item = require("vendor");\nitem();', Language.TYPESCRIPT)
    boundary = Boundary(name="blocked vendor", sources=("*.ts",), forbidden_imports=("vendor",))
    policy = Policy(checkers=Checkers(architecture_import=ImportOptions(boundaries=(boundary,))))
    findings = tuple(
        finding for finding in check(source, policy) if finding.rule == "architecture.import"
    )
    assert len(findings) == 1
    assert findings[0].line == 1
    assert findings[0].message == "blocked vendor: forbidden dependency vendor"


def test_selected_semantic_snapshot_takes_precedence_over_stale_reference() -> None:
    selected = Source(
        "app.py", b"def action(value: int) -> int:\n    return value\n", Language.PYTHON
    )
    stale = Source("app.py", b"def action(stale: int) -> int:\n    return 1\n", Language.PYTHON)
    registry = builtin_registry()
    assert registry.analyze_sources((selected,), Policy(), (stale,)) == registry.analyze_sources(
        (selected,), Policy()
    )


def test_conflicting_semantic_snapshots_fail_before_linking() -> None:
    first = Source("app.py", b"value: int = 1\n", Language.PYTHON)
    second = Source("app.py", b"value: str = 'second'\n", Language.PYTHON)
    with pytest.raises(AnalysisError, match="Conflicting semantic snapshots"):
        assert builtin_registry().analyze_sources((first, second), Policy()) == ()


class _RejectingSemanticParser(ContextParser):
    """Reject a snapshot while exposing parse lifetime for session recovery evidence."""

    def __init__(self) -> None:
        self.calls = 0

    def parse(self, source: Source, policy: Policy) -> TreeContext:
        self.calls += 1
        raise SyntaxFailure(
            (ParseWarning(path=source.path, line=1, column=1, message="semantic grammar rejected"),)
        )


def test_rejected_semantic_snapshot_is_parsed_and_warned_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    parser = _RejectingSemanticParser()
    bundles = BundleRegistry()
    bundles.register(BoundaryRule())
    analyzer = TypedAnalyzer(
        "rejected",
        LanguageDefinition(Language.PYTHON, (".py",)),
        parser,
        bundles,
        AnalysisProfile(("type.boundary",)),
        PythonSemanticSyntax(),
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    source = Source("rejected.py", b"invalid", Language.PYTHON)
    assert registry.analyze_sources((source, source), Policy()) == ()
    assert parser.calls == 1
    assert caplog.text.count("semantic grammar rejected") == 1
