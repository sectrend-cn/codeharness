"""Resolve Java serializer receiver types from explicit imported type declarations."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames


@dataclass(frozen=True)
class JavaEncodingTypes:
    """Use declared receiver contracts, never method spelling alone."""

    names: QualifiedNames

    def receiver(self, node: Node) -> str:
        if node.type == "object_creation_expression":
            return self.annotation(field(node, "type"))
        symbol = self.names.index.resolve(node)
        return self.annotation(symbol.annotation) if symbol is not None else ""

    def annotation(self, node: Node | None) -> str:
        if node is None:
            return ""
        if node.type == "generic_type":
            node = node.named_children[0]
        return self.names.qualified(node)
