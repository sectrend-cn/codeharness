"""Prove the lexical instance behind direct JavaScript this-member output calls."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.index import SemanticIndex


@dataclass(frozen=True)
class JavaScriptInstanceOutputs:
    """Keep dynamic this, static members and ambiguous declarations out of approvals."""

    index: SemanticIndex

    def owner(self, callee: Node) -> Node | None:
        receiver, member = self.index.syntax.member_parts(callee)
        if receiver is None or receiver.type != "this" or member is None:
            return None
        if member.type != "property_identifier" or self.index.context.root.has_error:
            return None
        owner = self._lexical_owner(callee)
        body = field(owner, "body") if owner is not None else None
        if body is None:
            return None
        return owner if self._declared_member(body, member) else None

    def _declared_member(self, body: Node, member: Node) -> bool:
        if any(
            name.type not in {"property_identifier", "private_property_identifier"}
            for child in body.named_children
            if (name := self._member_name(child)) is not None
        ):
            return False
        declarations = [
            child
            for child in body.named_children
            if (name := self._member_name(child)) is not None
            and self.index.text(name) == self.index.text(member)
        ]
        return len(declarations) == 1 and self._instance_declaration(declarations[0])

    def _member_name(self, node: Node) -> Node | None:
        return field(node, "name") or field(node, "property")

    def _lexical_owner(self, callee: Node) -> Node | None:
        current = callee.parent
        while current is not None:
            if current.type in {"method_definition", "public_field_definition", "field_definition"}:
                parent = current.parent
                if parent is None or parent.type != "class_body":
                    return None
                return parent.parent if self._instance_declaration(current) else None
            if self.index.syntax.function(current) and current.type != "arrow_function":
                return None
            if current.type in {"class", "class_declaration", "class_static_block"}:
                return None
            current = current.parent
        return None

    def _instance_declaration(self, node: Node) -> bool:
        return (
            node.type
            in {
                "method_definition",
                "public_field_definition",
                "field_definition",
            }
            and not self._explicit_receiver(node)
            and not any(
                child.type in {"static", "get", "set", "decorator"} for child in node.children
            )
        )

    def _explicit_receiver(self, node: Node) -> bool:
        parameters = field(node, "parameters")
        return parameters is not None and any(
            pattern.type == "this"
            for parameter in parameters.named_children
            if (pattern := field(parameter, "pattern")) is not None
        )
