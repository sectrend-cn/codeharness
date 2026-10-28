"""JavaScript, TypeScript and TSX guarded assignments and conditional spreads."""

from tree_sitter import Node

from code_harness.languages.projection_syntax import GrammarProjection
from code_harness.parsing.treesitter import field
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.projection.contracts import FieldKey, Guard, Primitive, Property


class JavaScriptProjection(GrammarProjection):
    """Keep undefined absence, loose nullish checks and strict literals distinct."""

    blocks = frozenset({"statement_block"})
    members = frozenset({"member_expression"})
    regions = frozenset({"program", "statement_block"})
    objects = frozenset({"object"})
    spreads = frozenset({"spread_element"})
    absent = frozenset({"undefined"})
    equal = frozenset({"===", "=="})
    unequal = frozenset({"!==", "!="})
    literal_equal = frozenset({"==="})

    def primitive(self, node: Node, index: SemanticIndex) -> Primitive | None:
        node = self.unwrap(node)
        if node.type in self.absent and self._hoisted_shadow(node, index):
            return None
        return super().primitive(node, index)

    def _hoisted_shadow(self, node: Node, index: SemanticIndex) -> bool:
        owners: set[int] = set()
        current: Node | None = node
        while current is not None:
            if index.syntax.function(current) or current == index.context.root:
                owners.add(current.id)
            current = current.parent
        return any(
            symbol.name == index.text(node) and self._variable_owner(symbol.node, index) in owners
            for symbol in index.symbols()
        )

    def _variable_owner(self, node: Node, index: SemanticIndex) -> int | None:
        parent = node.parent
        while parent is not None and parent.type in {
            "object_pattern",
            "array_pattern",
            "pair_pattern",
            "rest_pattern",
            "assignment_pattern",
        }:
            parent = parent.parent
        declaration = parent.parent if parent is not None else None
        if declaration is None or declaration.type != "variable_declaration":
            return None
        current = declaration.parent
        while current is not None:
            if index.syntax.function(current) or current == index.context.root:
                return current.id
            current = current.parent
        return None

    def _guard(self, member: Property, operator: str, literal: Primitive) -> Guard | None:
        if literal.kind == "absent" and operator not in {"===", "!=="}:
            return None
        if literal.kind == "null":
            if operator not in {"==", "!="}:
                return None
            return Guard(member, operator == "!=", literal, "nullish null/undefined")
        return super()._guard(member, operator, literal)

    def property(self, node: Node, index: SemanticIndex) -> Property | None:
        node = self.unwrap(node)
        if node.type != "subscript_expression":
            return super().property(node, index)
        receiver, key = field(node, "object"), field(node, "index")
        literal = self.primitive(key, index) if key is not None else None
        if receiver is not None and literal is not None and literal.kind == "string":
            return Property(receiver, FieldKey(literal.value))
        return None

    def _key(self, node: Node, index: SemanticIndex) -> str | None:
        if node.type != "computed_property_name":
            key = super()._key(node, index)
            return None if key == "__proto__" else key
        children = self._children(node)
        literal = self.primitive(children[0], index) if len(children) == 1 else None
        return literal.value if literal is not None and literal.kind == "string" else None

    def immutable_alias(self, node: Node) -> bool:
        parent = node.parent
        declaration = parent.parent if parent is not None else None
        return (
            parent is not None
            and parent.type == "variable_declarator"
            and declaration is not None
            and declaration.type == "lexical_declaration"
            and any(child.type == "const" for child in declaration.children)
        )
