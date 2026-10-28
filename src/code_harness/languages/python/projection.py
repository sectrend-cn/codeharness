"""Python None/literal guards and conditional dictionary unpacking."""

from tree_sitter import Node

from code_harness.languages.projection_syntax import GrammarProjection
from code_harness.parsing.treesitter import field
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.projection.contracts import (
    Branches,
    FieldKey,
    Guard,
    Primitive,
    Property,
)


class PythonProjection(GrammarProjection):
    """Match explicit None tests without interpreting truthiness or validation calls."""

    entry_access = "item"
    members = frozenset({"attribute"})
    regions = frozenset({"module", "block"})
    objects = frozenset({"dictionary"})
    spreads = frozenset({"dictionary_splat"})
    assignments = frozenset({"assignment"})
    numbers = frozenset({"integer", "float"})
    nulls = frozenset({"none"})
    equal = frozenset({"is", "=="})
    unequal = frozenset({"is not", "!="})
    literal_equal = frozenset({"==", "is"})

    def _string(self, node: Node, value: str) -> Primitive | None:
        if len(value) >= 3 and value[:3] == value[0] * 3:
            return None
        return super()._string(node, value)

    def _key(self, node: Node, index: SemanticIndex) -> str | None:
        literal = self.primitive(node, index)
        return literal.value if literal is not None and literal.kind == "string" else None

    def _guard(self, member: Property, operator: str, literal: Primitive) -> Guard | None:
        if operator == "is" and literal.kind not in {"boolean", "null"}:
            return None
        return super()._guard(member, operator, literal)

    def _comparison(self, node: Node) -> tuple[Node, str, Node] | None:
        node = self.unwrap(node)
        children = self._children(node)
        if node.type != "comparison_operator" or len(children) != 2:
            return None
        operators = node.children_by_field_name("operators")
        if len(operators) != 1:
            return None
        return children[0], operators[0].type, children[1]

    def _expression(self, node: Node) -> Branches | None:
        children = self._children(node)
        if node.type == "conditional_expression" and len(children) == 3:
            return Branches(children[1], children[0], children[2])
        return None

    def empty(self, node: Node | None) -> bool:
        return (node is not None and self._action(node).type == "pass_statement") or super().empty(
            node
        )

    def property(self, node: Node, index: SemanticIndex) -> Property | None:
        node = self.unwrap(node)
        if node.type != "subscript":
            return super().property(node, index)
        keys = node.children_by_field_name("subscript")
        if len(keys) != 1 or any(child.type == "," for child in node.children):
            return None
        receiver, key = field(node, "value"), keys[0]
        literal = self.primitive(key, index)
        if receiver is not None and literal is not None and literal.kind == "string":
            return Property(receiver, FieldKey(literal.value, "item"))
        return None
