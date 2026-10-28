"""Reusable grammar operations for guarded field projection adapters."""

from typing import Literal

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.projection.contracts import (
    Branches,
    FieldKey,
    Guard,
    Primitive,
    Property,
    Write,
)


class GrammarProjection:
    """Interpret explicit tree shapes; language owners declare supported syntax."""

    entry_access: Literal["member", "item"] = "member"
    members = frozenset({"field_access"})
    blocks = frozenset({"block"})
    regions = frozenset({"block"})
    objects = frozenset[str]()
    spreads = frozenset[str]()
    assignments = frozenset({"assignment_expression"})
    strings = frozenset({"string"})
    numbers = frozenset({"number"})
    booleans = frozenset({"true", "false"})
    nulls = frozenset({"null"})
    absent = frozenset[str]()
    equal = frozenset({"=="})
    unequal = frozenset({"!="})
    literal_equal = frozenset({"=="})

    def region(self, node: Node) -> bool:
        return node.type in self.regions or self.construction(node)

    def construction(self, node: Node) -> bool:
        return node.type in self.objects

    def ignored(self, node: Node) -> bool:
        return node.type in {"comment", "line_comment", "block_comment", "empty_statement"}

    def _children(self, node: Node) -> tuple[Node, ...]:
        return tuple(child for child in node.named_children if not self.ignored(child))

    def unwrap(self, node: Node) -> Node:
        while node.type in {"parenthesized_expression", "expression_list"}:
            children = self._children(node)
            if len(children) != 1:
                break
            node = children[0]
        return node

    def branches(self, node: Node) -> Branches | None:
        if node.type in self.spreads:
            children = self._children(node)
            return self._expression(self.unwrap(children[0])) if len(children) == 1 else None
        if node.type != "if_statement" or field(node, "initializer") is not None:
            return None
        condition, action = field(node, "condition"), field(node, "consequence")
        if condition is None or action is None:
            return None
        return Branches(condition, action, field(node, "alternative"))

    def _expression(self, node: Node) -> Branches | None:
        condition = field(node, "condition")
        action, alternative = field(node, "consequence"), field(node, "alternative")
        if condition is not None and action is not None and alternative is not None:
            return Branches(condition, action, alternative)
        operator = field(node, "operator")
        left, right = field(node, "left"), field(node, "right")
        if operator is not None and operator.type == "&&" and left is not None and right:
            return Branches(left, right, None)
        return None

    def _comparison(self, node: Node) -> tuple[Node, str, Node] | None:
        node = self.unwrap(node)
        left, right, operator = field(node, "left"), field(node, "right"), field(node, "operator")
        if left is None or right is None or operator is None:
            return None
        return left, operator.type, right

    def guard(self, node: Node, index: SemanticIndex) -> Guard | None:
        comparison = self._comparison(node)
        if comparison is None:
            return None
        left, operator, right = comparison
        member, literal = self.property(left, index), self.primitive(right, index)
        if member is None or literal is None:
            member, literal = self.property(right, index), self.primitive(left, index)
        if member is None or literal is None:
            return None
        return self._guard(member, operator, literal)

    def _guard(self, member: Property, operator: str, literal: Primitive) -> Guard | None:
        if literal.kind in {"null", "absent"}:
            if operator not in self.equal | self.unequal:
                return None
            return Guard(member, operator in self.unequal, literal, f"presence {literal.value}")
        if operator in self.literal_equal:
            return Guard(member, True, literal, f"equality {literal.value}")
        return None

    def _action(self, node: Node) -> Node:
        node = self.unwrap(node)
        while node.type in self.blocks | {"expression_statement", "else_clause"}:
            children = self._children(node)
            if len(children) != 1:
                break
            node = self.unwrap(children[0])
        return node

    def empty(self, node: Node | None) -> bool:
        if node is None:
            return True
        node = self._action(node)
        return self.ignored(node) or (
            node.type in self.blocks | self.objects and not self._children(node)
        )

    def write(self, node: Node, construction: bool, index: SemanticIndex) -> Write | None:
        node = self._action(node)
        if construction:
            return self._entry(node, index)
        if node.type not in self.assignments:
            return None
        operators = [child.type for child in node.children if not child.is_named]
        if operators != ["="]:
            return None
        left, right = field(node, "left"), field(node, "right")
        member = self.property(left, index) if left is not None else None
        if member is None or right is None:
            return None
        return Write(member.receiver, member.key, self.unwrap(right))

    def _entry(self, node: Node, index: SemanticIndex) -> Write | None:
        children = self._children(node)
        if not self.construction(node) or len(children) != 1 or children[0].type != "pair":
            return None
        key, value = field(children[0], "key"), field(children[0], "value")
        name = self._key(key, index) if key is not None else None
        return (
            Write(None, FieldKey(name, self.entry_access), value)
            if name is not None and value is not None
            else None
        )

    def property(self, node: Node, index: SemanticIndex) -> Property | None:
        node = self.unwrap(node)
        if node.type not in self.members:
            return None
        receiver, member = index.syntax.member_parts(node)
        if receiver is None or member is None:
            return None
        return Property(receiver, FieldKey(index.text(member)))

    def _key(self, node: Node, index: SemanticIndex) -> str | None:
        if node.type in {"identifier", "property_identifier"}:
            return index.text(node)
        literal = self.primitive(node, index)
        return literal.value if literal is not None and literal.kind == "string" else None

    def primitive(self, node: Node, index: SemanticIndex) -> Primitive | None:
        node = self.unwrap(node)
        value = index.text(node)
        if node.type in self.nulls:
            return Primitive("null", value)
        if node.type in self.absent:
            scope = index.locations.get(node.id, 0)
            return Primitive("absent", value) if index.lookup(value, scope) is None else None
        if node.type in self.booleans:
            return Primitive("boolean", value)
        if node.type in self.numbers:
            return Primitive("number", value)
        return self._signed(node, index) or self._string(node, value)

    def _signed(self, node: Node, index: SemanticIndex) -> Primitive | None:
        if node.type not in {"unary_expression", "unary_operator"}:
            return None
        children = self._children(node)
        operators = tuple(child.type for child in node.children if not child.is_named)
        if len(children) != 1 or operators not in {("-",), ("+",)}:
            return None
        number = self.unwrap(children[0])
        if number.type not in self.numbers:
            return None
        return Primitive("number", operators[0] + index.text(number))

    def _string(self, node: Node, value: str) -> Primitive | None:
        if node.type in self.strings and "\\" not in value and "\n" not in value:
            if len(value) >= 2 and value[0] in {"'", '"', "`"} and value[-1] == value[0]:
                return Primitive("string", value[1:-1])
        return None

    def immutable_alias(self, node: Node) -> bool:
        return False

    def destination(self, node: Node, index: SemanticIndex) -> str:
        parent = node.parent
        while parent is not None and parent.type == "parenthesized_expression":
            parent = parent.parent
        if parent is not None and parent.type == "return_statement":
            return "returned object"
        name = field(parent, "name") if parent is not None else None
        if name is not None:
            return index.text(name)
        return f"object at {node.start_point.row + 1}:{node.start_point.column + 1}"
