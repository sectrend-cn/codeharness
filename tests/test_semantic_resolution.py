"""Semantic resolution owns reusable evidence independently of rule execution."""

from collections.abc import Callable

import pytest
import tree_sitter_go
import tree_sitter_javascript
import tree_sitter_python
from tree_sitter import Language as Grammar

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import RuleBundle
from code_harness.analysis.session import AnalysisSession, SemanticBinding
from code_harness.diagnostics import AnalysisError, Finding
from code_harness.languages.go.semantic_syntax import GoSemanticSyntax
from code_harness.languages.javascript.semantic_syntax import JavaScriptSemanticSyntax
from code_harness.languages.python.encoding import PythonEncodingSyntax
from code_harness.languages.python.rules import PythonTypeRule
from code_harness.languages.python.semantic_syntax import PythonSemanticSyntax
from code_harness.parsing.treesitter import TreeParser
from code_harness.policy.models import Policy
from code_harness.semantics.boundaries import BoundaryEvidence, BoundaryRule
from code_harness.semantics.encoding import EncodingRule
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import Symbol
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


_GO_ELEMENT_WRITE = """package main

type Item struct{}

type Other struct{}

func (o Other) write() int { return 1 }

func main() {
	items := []Item{{}}
	items[0] = Other{}
}
"""

_GO_ANNOTATED_ELEMENT_WRITE = """package main

type Item struct{}

type Other struct{}

func (o Other) write() int { return 1 }

func Run() {
	var items []Item
	items[0] = Other{}
}
"""

_PYTHON_ELEMENT_WRITE = """class Item:
    pass


class Other:
    def write(self) -> int:
        return 1


def run() -> None:
    items = [Item()]
    items[0] = Other()
"""

_PYTHON_ANNOTATED_ELEMENT_WRITE = """class Item:
    pass


class Other:
    def write(self) -> int:
        return 1


def run() -> None:
    items: list[Item] = []
    items[0] = Other()
"""


def _go_index(code: str, path: str = "sample.go") -> SemanticIndex:
    source = Source(path, code.encode(), Language.GO)
    parser = TreeParser(Grammar(tree_sitter_go.language()))
    context = TreeContext(source, parser.tree(source), Policy())
    return SemanticIndex(context, GoSemanticSyntax())


def _container(index: SemanticIndex, name: str) -> Symbol:
    return next(symbol for symbol in index.symbols() if symbol.name == name)


def _assert_element_ownership(index: SemanticIndex, element_type: str) -> tuple[Finding, ...]:
    symbol = _container(index, "items")
    assert [node.type for node in symbol.writes] == ["identifier", element_type]
    assert symbol.type_name == "Item"
    assert symbol.class_scope is not None
    assert symbol.class_scope.owner == "Item"
    return UsageRule().evaluate(index)


@pytest.mark.parametrize(
    ("builder", "code", "element_type"),
    [
        pytest.param(_go_index, _GO_ELEMENT_WRITE, "index_expression", id="go-value"),
        pytest.param(
            _go_index, _GO_ANNOTATED_ELEMENT_WRITE, "index_expression", id="go-annotation"
        ),
        pytest.param(_index, _PYTHON_ELEMENT_WRITE, "subscript", id="python-value"),
        pytest.param(_index, _PYTHON_ANNOTATED_ELEMENT_WRITE, "subscript", id="python-annotation"),
    ],
)
def test_element_writes_keep_the_container_symbol_ownership(
    builder: Callable[[str], SemanticIndex], code: str, element_type: str
) -> None:
    index = builder(code)
    first = _assert_element_ownership(index, element_type)
    assert [finding.rule for finding in first] == ["unused.function"]
    index.refresh()
    index.refresh()
    assert _assert_element_ownership(index, element_type) == first


_GO_PARENTHESIZED_ELEMENT_WRITE = """package main

type Item struct{}

type Other struct{}

func (o Other) write() int { return 1 }

func main() {
	items := []Item{{}}
	(items[0]) = Other{}
}
"""

_PYTHON_PARENTHESIZED_ELEMENT_WRITE = """class Item:
    pass


class Other:
    def write(self) -> int:
        return 1


def run() -> None:
    items = [Item()]
    (items[0]) = Other()
"""


def _assert_parenthesized_element_ownership(
    index: SemanticIndex, target_type: str, element_type: str, finding_line: int
) -> None:
    symbol = _container(index, "items")
    assert [node.type for node in symbol.writes] == ["identifier", target_type]
    assert index.syntax.single_value(symbol.writes[1]).type == element_type
    assert index.syntax.element_target(symbol.writes[1])
    assert symbol.type_name == "Item"
    assert symbol.class_scope is not None
    assert symbol.class_scope.owner == "Item"
    assert [(finding.rule, finding.line) for finding in UsageRule().evaluate(index)] == [
        ("unused.function", finding_line)
    ]


@pytest.mark.parametrize(
    ("builder", "code", "target_type", "element_type", "finding_line"),
    [
        pytest.param(
            _go_index,
            _GO_PARENTHESIZED_ELEMENT_WRITE,
            "parenthesized_expression",
            "index_expression",
            7,
            id="go-parenthesized",
        ),
        pytest.param(
            _index,
            _PYTHON_PARENTHESIZED_ELEMENT_WRITE,
            "subscript",
            "subscript",
            6,
            id="python-tuple-pattern",
        ),
    ],
)
def test_parenthesized_element_writes_keep_the_container_symbol_ownership(
    builder: Callable[[str], SemanticIndex],
    code: str,
    target_type: str,
    element_type: str,
    finding_line: int,
) -> None:
    index = builder(code)
    _assert_parenthesized_element_ownership(index, target_type, element_type, finding_line)
    first = tuple((node.id, node.type) for node in _container(index, "items").writes)
    index.refresh()
    index.refresh()
    _assert_parenthesized_element_ownership(index, target_type, element_type, finding_line)
    assert tuple((node.id, node.type) for node in _container(index, "items").writes) == first


_PYTHON_SHADOWED_ELEMENT = """class Item:
    def render(self) -> int:
        return 1

class Other:
    def render(self) -> int:
        return 2

def run(Item: type[Other]) -> None:
    xs = [Item()]
    xs[0].render()
"""

_JAVASCRIPT_SHADOWED_ELEMENT = """class Item {
    render() { return 1; }
}

class Other {
    render() { return 2; }
}

export function run(Item) {
    const xs = [new Item()];
    xs[0].render();
}
"""

_JAVASCRIPT_VARIABLE_SHADOWED_ELEMENT = """class Item {
    render() { return 1; }
}

class Other {
    render() { return 2; }
}

export function run() {
    const Item = Other;
    const xs = [new Item()];
    xs[0].render();
}
"""


def _javascript_index(code: str, path: str = "sample.js") -> SemanticIndex:
    source = Source(path, code.encode(), Language.JAVASCRIPT)
    parser = TreeParser(Grammar(tree_sitter_javascript.language()))
    context = TreeContext(source, parser.tree(source), Policy(third_party_modules=("vendor",)))
    return SemanticIndex(context, JavaScriptSemanticSyntax())


def _assert_shadowed_element_stays_unresolved(index: SemanticIndex) -> None:
    symbol = _container(index, "xs")
    assert symbol.type_name == ""
    assert symbol.class_scope is None
    assert [(node.type, index.syntax.element_target(node)) for node in symbol.writes] == [
        ("identifier", False)
    ]
    assert UsageRule().evaluate(index) == ()


@pytest.mark.parametrize(
    ("builder", "code"),
    [
        pytest.param(_index, _PYTHON_SHADOWED_ELEMENT, id="python-parameter"),
        pytest.param(_javascript_index, _JAVASCRIPT_SHADOWED_ELEMENT, id="javascript-parameter"),
        pytest.param(
            _javascript_index,
            _JAVASCRIPT_VARIABLE_SHADOWED_ELEMENT,
            id="javascript-variable",
        ),
    ],
)
def test_shadowed_element_names_leave_no_container_ownership(
    builder: Callable[[str], SemanticIndex], code: str
) -> None:
    """A vetoed spelled name leaves the element type unresolved (DESIGN §13.1)."""
    index = builder(code)
    _assert_shadowed_element_stays_unresolved(index)
    index.refresh()
    index.refresh()
    _assert_shadowed_element_stays_unresolved(index)


_JAVASCRIPT_COMMENTED_ELEMENT_WRITE = """class Item {
    m() { return 1; }
}

class Other {
    m() { return 2; }
}

const items = [new Item()];
(/* keep */ items[0]) = new Other();
items[1].m();
"""


def _assert_commented_element_ownership(index: SemanticIndex) -> None:
    symbol = _container(index, "items")
    assert [node.type for node in symbol.writes] == ["identifier", "parenthesized_expression"]
    assert index.syntax.element_target(symbol.writes[1])
    assert index.syntax.single_value(symbol.writes[1]).type == "subscript_expression"
    assert symbol.type_name == "Item"
    assert symbol.class_scope is not None
    assert symbol.class_scope.owner == "Item"
    assert [(finding.rule, finding.line) for finding in UsageRule().evaluate(index)] == [
        ("unused.function", 6),
        ("unused.return", 11),
    ]


def test_commented_element_write_keeps_the_container_ownership() -> None:
    """A comment before the element target stays out of the unpacked value (DESIGN §13.2)."""
    index = _javascript_index(_JAVASCRIPT_COMMENTED_ELEMENT_WRITE)
    _assert_commented_element_ownership(index)
    writes = tuple((node.id, node.type) for node in _container(index, "items").writes)
    index.refresh()
    index.refresh()
    _assert_commented_element_ownership(index)
    assert tuple((node.id, node.type) for node in _container(index, "items").writes) == writes


_JAVASCRIPT_COMMENTED_ELEMENT_INGRESS = """import {fetch} from "vendor";
const items = [0];
(items[0] /* keep */) = fetch();
console.log(items);
"""


def test_commented_element_ingress_write_keeps_the_element_target() -> None:
    """A comment after the element target still records the element write (DESIGN §13.2)."""
    index = _javascript_index(_JAVASCRIPT_COMMENTED_ELEMENT_INGRESS)
    symbol = _container(index, "items")
    assert [node.type for node in symbol.writes] == ["identifier", "parenthesized_expression"]
    assert index.syntax.element_target(symbol.writes[1])
    assert index.syntax.single_value(symbol.writes[1]).type == "subscript_expression"
    assert symbol.class_scope is None


_GO_MAP_TYPE_CLASSES = """package sample

type key struct{}

type item struct{}

func (k key) render() int { return 1 }

func (i item) render() int { return 2 }
"""

_GO_COMMENTED_POINTER_MAP_ANNOTATION = (
    _GO_MAP_TYPE_CLASSES
    + """
var xs []* /* keep */ map[key]item

func Run() {
\txs[0]["k"].render()
}
"""
)

_GO_PARENTHESIZED_POINTER_MAP_ANNOTATION = (
    _GO_MAP_TYPE_CLASSES
    + """
var xs []*(map[key]item)

func Run() {
\txs[0]["k"].render()
}
"""
)


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(_GO_COMMENTED_POINTER_MAP_ANNOTATION, id="comment"),
        pytest.param(_GO_PARENTHESIZED_POINTER_MAP_ANNOTATION, id="type-parentheses"),
    ],
)
def test_commented_pointer_map_annotations_keep_the_value_owner(code: str) -> None:
    """Reduction skips comments and type parentheses without fixing the key type name."""
    index = _go_index(code)
    symbol = _container(index, "xs")
    assert symbol.class_scope is not None
    assert symbol.class_scope.owner == "item"
    assert [(node.type, index.syntax.element_target(node)) for node in symbol.writes] == [
        ("identifier", False)
    ]
    assert [(finding.rule, finding.line) for finding in UsageRule().evaluate(index)] == [
        ("unused.function", 7),
        ("unused.return", 14),
    ]


_GO_COMMENTED_POINTER_MAP_VALUE = (
    _GO_MAP_TYPE_CLASSES
    + """
func Run() {
\txs := []* /* keep */ map[key]item{{}}
\txs[0]["k"].render()
}
"""
)

_GO_ITEM_TYPE = """package sample

type item struct{}

func (i item) render() int { return 2 }
"""

_GO_COMMENTED_MAKE = (
    _GO_ITEM_TYPE
    + """
func Run() {
\txs := make(/* keep */ []item, 1)
\txs[0].render()
}
"""
)

_GO_POINTER_ITEM_TYPE = """package sample

type item struct{}

func (i *item) render() int { return 2 }
"""

_GO_COMMENTED_NEW = (
    _GO_POINTER_ITEM_TYPE
    + """
func Run() {
\tp := new(/* keep */ item)
\tp.render()
}
"""
)

_GO_PARENTHESIZED_MAKE_TYPE = (
    _GO_MAP_TYPE_CLASSES
    + """
func Run() {
\tm := make((map[key]item), 1)
\tm["k"].render()
}
"""
)


@pytest.mark.parametrize(
    ("code", "name"),
    [
        pytest.param(_GO_COMMENTED_POINTER_MAP_VALUE, "xs", id="composite-literal"),
        pytest.param(_GO_COMMENTED_MAKE, "xs", id="make"),
        pytest.param(_GO_COMMENTED_NEW, "p", id="new"),
        pytest.param(_GO_PARENTHESIZED_MAKE_TYPE, "m", id="make-type-parentheses"),
    ],
)
def test_commented_go_value_types_keep_the_value_owner(code: str, name: str) -> None:
    """Comments inside spelled Go types do not change the inferred element owner."""
    index = _go_index(code)
    symbol = _container(index, name)
    assert symbol.type_name == "item"
    assert symbol.class_scope is not None
    assert symbol.class_scope.owner == "item"


_GO_POINTER_DEREFERENCE_WRITE = """package main

type item struct{}

type other struct{}

func (i item) m() {}

func (o other) m() {}

func main() {
\tp := &item{}
\t*p = other{}
\tp.m()
}
"""


def test_pointer_dereference_write_pins_the_registered_overwrite() -> None:
    """Pin the registered pointer-dereference overwrite (PROJECT §10.6, DESIGN §13.3)."""
    index = _go_index(_GO_POINTER_DEREFERENCE_WRITE)
    symbol = _container(index, "p")
    assert [(node.type, index.syntax.element_target(node)) for node in symbol.writes] == [
        ("identifier", False),
        ("unary_expression", False),
    ]
    assert symbol.type_name == "other"
    assert symbol.class_scope is not None
    assert symbol.class_scope.owner == "other"
    assert [(finding.rule, finding.line) for finding in UsageRule().evaluate(index)] == [
        ("unused.function", 7)
    ]
