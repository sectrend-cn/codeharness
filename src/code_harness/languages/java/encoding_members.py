"""Resolve explicit Java this calls and imported Consumer callback fields."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.languages.alias_syntax import GrammarNames
from code_harness.languages.java.encoding_types import JavaEncodingTypes
from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames
from code_harness.semantics.index import SemanticIndex


@dataclass(frozen=True)
class JavaInstanceOutputs:
    """Separate callable field ownership from its functional-interface invocation."""

    index: SemanticIndex

    def member(self, callee: Node) -> Node | None:
        receiver, name = self.index.syntax.member_parts(callee)
        if receiver is not None and receiver.type == "field_access":
            return field(receiver, "field")
        return name

    def owner(self, callee: Node) -> Node | None:
        receiver = self._receiver(callee)
        if receiver is None or receiver.type != "this":
            return None
        owner = self._lexical_owner(callee)
        member = self.member(callee)
        if owner is None or member is None:
            return None
        return (
            owner
            if self._declared(owner, self.index.text(member), receiver != field(callee, "object"))
            else None
        )

    def _receiver(self, callee: Node) -> Node | None:
        receiver, name = self.index.syntax.member_parts(callee)
        if receiver is None or name is None or self.index.context.root.has_error:
            return None
        if receiver.type == "field_access":
            if not self._consumer(receiver, name):
                return None
            receiver = field(receiver, "object")
        return receiver

    def _consumer(self, receiver: Node, name: Node) -> bool:
        names = QualifiedNames(self.index, GrammarNames())
        return (
            self.index.text(name) == "accept"
            and JavaEncodingTypes(names).receiver(receiver) == "java.util.function.Consumer"
        )

    def _lexical_owner(self, callee: Node) -> Node | None:
        current = callee.parent
        while current is not None:
            if current.type == "static_initializer" or self._static(current):
                return None
            if current.type == "class_body":
                owner = current.parent
                return owner if owner is not None and owner.type == "class_declaration" else None
            current = current.parent
        return None

    def _declared(self, owner: Node, name: str, callback: bool) -> bool:
        body = field(owner, "body")
        if body is None:
            return False
        declarations = [
            declaration for child in body.named_children for declaration in self._named(child, name)
        ]
        if len(declarations) != 1 or self._static(declarations[0]):
            return False
        expected = "field_declaration" if callback else "method_declaration"
        return declarations[0].type == expected

    def _named(self, node: Node, name: str) -> tuple[Node, ...]:
        declared = field(node, "name")
        if declared is not None:
            return (node,) if self.index.text(declared) == name else ()
        return tuple(
            node
            for child in node.children_by_field_name("declarator")
            if (declared := field(child, "name")) is not None and self.index.text(declared) == name
        )

    def _static(self, node: Node) -> bool:
        return any(
            token.type == "static"
            for child in node.named_children
            if child.type == "modifiers"
            for token in child.children
        )
