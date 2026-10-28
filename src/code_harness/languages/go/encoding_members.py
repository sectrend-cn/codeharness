"""Resolve Go output methods and function fields on a declared method receiver."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import Scope


@dataclass(frozen=True)
class GoInstanceOutputs:
    """Require the same lexical receiver binding and a direct named struct member."""

    index: SemanticIndex

    def owner(self, callee: Node) -> Node | None:
        receiver, member = self.index.syntax.member_parts(callee)
        if receiver is None or member is None or self.index.context.root.has_error:
            return None
        owner = self._receiver(receiver)
        if owner is None or not self._declared(owner, self.index.text(member)):
            return None
        return owner.node

    def _receiver(self, receiver: Node) -> Scope | None:
        symbol = self.index.resolve(receiver)
        if symbol is None or symbol.writes or receiver.type != "identifier":
            return None
        method = self.index.scopes[symbol.scope].node
        declared = self.index.syntax.receivers(method)
        if len(declared) != 1 or declared[0][0] != symbol.node:
            return None
        return symbol.class_scope

    def _declared(self, owner: Scope, name: str) -> bool:
        structure = field(owner.node, "type")
        if structure is None or structure.type != "struct_type":
            return False
        fields = self._fields(structure, name)
        methods = [
            node
            for node in self.index.context.root.named_children
            if node.type == "method_declaration" and self._method(node, owner, name)
        ]
        if methods:
            return len(methods) == 1 and not fields
        if len(fields) != 1:
            return False
        annotation = field(fields[0], "type")
        return annotation is not None and annotation.type == "function_type"

    def _fields(self, structure: Node, name: str) -> tuple[Node, ...]:
        return tuple(
            node
            for group in structure.named_children
            if group.type == "field_declaration_list"
            for node in group.named_children
            if node.type == "field_declaration"
            for declared in node.children_by_field_name("name")
            if self.index.text(declared) == name
        )

    def _method(self, node: Node, owner: Scope, name: str) -> bool:
        declared = field(node, "name")
        receivers = self.index.syntax.receivers(node)
        if declared is None or self.index.text(declared) != name or len(receivers) != 1:
            return False
        symbol = self.index.resolve(receivers[0][0])
        return symbol is not None and symbol.class_scope is owner
