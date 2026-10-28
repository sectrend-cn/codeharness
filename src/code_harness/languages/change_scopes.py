"""Interpret definition and class-header extents in built-in tree grammars."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.model import BindingSyntax


@dataclass(frozen=True)
class GrammarScopes:
    """Reuse declaration identity while keeping grammar wrappers with languages."""

    bindings: BindingSyntax

    def definition(self, node: Node) -> bool:
        return self.bindings.function(self._declaration(node))

    def extent(self, node: Node) -> Node:
        parent = node.parent
        if parent is not None and parent.type in {"decorated_definition", "export_statement"}:
            return parent
        return node

    def header_end(self, node: Node) -> int | None:
        node = self._declaration(node)
        if self.bindings.class_name(node) is None:
            return None
        body = field(node, "body")
        if body is None:
            return node.end_point.row + 1
        first = next((child for child in body.named_children if child.type != "comment"), None)
        return first.start_point.row if first is not None else body.end_point.row + 1

    def _declaration(self, node: Node) -> Node:
        if node.type in {"decorated_definition", "export_statement"}:
            return next(
                (
                    child
                    for child in node.named_children
                    if self.bindings.function(child) or self.bindings.class_name(child) is not None
                ),
                node,
            )
        return node
