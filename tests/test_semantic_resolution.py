"""Semantic resolution owns reusable evidence independently of rule execution."""

import pytest
import tree_sitter_python
from tree_sitter import Language as Grammar

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import RuleBundle
from code_harness.analysis.session import AnalysisSession, SemanticBinding
from code_harness.diagnostics import AnalysisError
from code_harness.languages.python.encoding import PythonEncodingSyntax
from code_harness.languages.python.rules import PythonTypeRule
from code_harness.languages.python.semantic_syntax import PythonSemanticSyntax
from code_harness.parsing.treesitter import TreeParser
from code_harness.policy.models import Policy
from code_harness.semantics.boundaries import BoundaryEvidence, BoundaryRule
from code_harness.semantics.encoding import EncodingRule
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.project import ProjectUsage
from code_harness.semantics.usage import UsageRule
from code_harness.source import Language, Source


def _index(code: str, path: str = "sample.py") -> SemanticIndex:
    source = Source(path, code.encode(), Language.PYTHON)
    parser = TreeParser(Grammar(tree_sitter_python.language()))
    context = TreeContext(source, parser.tree(source), Policy(third_party_modules=("vendor",)))
    return SemanticIndex(context, PythonSemanticSyntax())


def test_refresh_preserves_single_assignment_boundary_evidence() -> None:
    index = _index(
        "import vendor\n"
        "def send(value: int) -> None:\n"
        "    payload = {'value': value}\n"
        "    vendor.send(payload)\n"
    )
    payload = next(symbol for symbol in index.symbols() if symbol.name == "payload")
    before = (tuple(payload.reads), tuple(payload.writes))
    index.refresh()
    index.refresh()
    assert (tuple(payload.reads), tuple(payload.writes)) == before
    assert len(payload.writes) == 1
    assert payload.value is not None
    assert BoundaryEvidence(index).is_library_input(payload.value)


def test_project_preparation_preserves_cross_file_reads_and_unique_bases() -> None:
    base = _index(
        "class Base:\n    def value(self, used: int) -> int:\n        return used\n", "base.py"
    )
    child = _index(
        "from base import Base\n"
        "class Child(Base):\n"
        "    def value(self, used: int) -> int:\n"
        "        return 0\n",
        "child.py",
    )
    project = ProjectUsage((base, child))
    project.prepare()
    child_scope = child.class_scope("Child")
    assert child_scope is not None
    assert len(child_scope.bases) == 1
    declarations = tuple(base.symbols()) + tuple(child.symbols())
    before = tuple((tuple(symbol.reads), tuple(symbol.writes)) for symbol in declarations)
    project.prepare()
    first = project.evidence()
    assert project.evidence() == first
    findings = UsageRule().evaluate(child, first.unresolved, first.contract_reads)
    assert not any(finding.rule == "unused.parameter" for finding in findings)
    assert tuple((tuple(symbol.reads), tuple(symbol.writes)) for symbol in declarations) == before


def test_project_rejects_evaluation_without_preparation() -> None:
    project = ProjectUsage((_index("value = 1\n"),))
    with pytest.raises(AnalysisError, match="must be prepared"):
        assert project.evidence().unresolved == frozenset()


def test_semantic_and_type_rule_order_reuses_prepared_boundary_evidence() -> None:
    source = Source(
        "sample.py",
        b"import vendor\ndef send(value: int) -> None:\n"
        b"    payload: dict[str, object] = {'value': value}\n"
        b"    vendor.send(payload)\n",
        Language.PYTHON,
    )
    parser = TreeParser(Grammar(tree_sitter_python.language()))
    session = AnalysisSession(Policy(third_party_modules=("vendor",)))
    session.prepare((source,), {Language.PYTHON: SemanticBinding(parser, PythonSemanticSyntax())})
    context = session.context(source, parser)
    index, boundary = context.require_index(), context.require_boundary()
    before = tuple((tuple(symbol.reads), tuple(symbol.writes)) for symbol in index.symbols())
    rules: tuple[RuleBundle, ...] = (
        UsageRule(),
        BoundaryRule(),
        PythonTypeRule(EncodingRule(PythonEncodingSyntax())),
    )
    forward = tuple(finding for rule in rules for finding in rule.check(context))
    backward = tuple(finding for rule in reversed(rules) for finding in rule.check(context))
    assert set(forward) == set(backward)
    assert not any(finding.rule == "type.annotation" for finding in forward)
    assert context.require_boundary() is boundary
    assert context.require_index() is index
    assert (
        tuple((tuple(symbol.reads), tuple(symbol.writes)) for symbol in index.symbols()) == before
    )
