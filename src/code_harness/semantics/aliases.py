"""Resolve stable callable and module aliases through canonical lexical symbols."""

from typing import Protocol

from tree_sitter import Node

from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import ImportedName


class NameSyntax(Protocol):
    """Interpret transparent expressions, imports and unbound built-in names."""

    def transparent(self, node: Node) -> Node | None: ...
    def imported(self, entry: ImportedName) -> str: ...
    def builtin(self, name: str) -> bool: ...


class QualifiedNames:
    """Follow single-assignment aliases with cycle and lexical-shadow protection."""

    def __init__(self, index: SemanticIndex, syntax: NameSyntax) -> None:
        self.index = index
        self.syntax = syntax
        self.imports = {entry.node.id: entry for entry in index.syntax.imports(index.context)}

    def qualified(self, node: Node, seen: frozenset[int] = frozenset()) -> str:
        if node.id in seen:
            return ""
        seen = seen | {node.id}
        transparent = self.syntax.transparent(node)
        if transparent is not None:
            return self.qualified(transparent, seen)
        if self.index.syntax.member_expression(node):
            return self._member(node, seen)
        return self._binding(node, seen)

    def _member(self, node: Node, seen: frozenset[int]) -> str:
        receiver, member = self.index.syntax.member_parts(node)
        if receiver is None or member is None:
            return ""
        prefix = self.qualified(receiver, seen)
        return f"{prefix}.{self.index.text(member)}" if prefix else ""

    def _binding(self, node: Node, seen: frozenset[int]) -> str:
        symbol = self.index.resolve(node)
        if symbol is None:
            name = self.index.text(node)
            return name if self.index.syntax.identifier(node) and self.syntax.builtin(name) else ""
        imported = self.imports.get(symbol.node.id)
        if imported is not None:
            return self.syntax.imported(imported)
        value = self.assigned(node)
        return self.qualified(value, seen) if value is not None else ""

    def assigned(self, node: Node) -> Node | None:
        """Require one concrete local assignment before following its value."""
        symbol = self.index.resolve(node)
        if symbol is None or symbol.kind != "variable" or len(symbol.writes) != 1:
            return None
        return symbol.value

    def value(self, node: Node) -> Node | None:
        """Resolve a stable value chain for consumers that inspect constructor provenance."""
        seen: set[int] = set()
        while node.id not in seen:
            seen.add(node.id)
            value = self.syntax.transparent(node) or self.assigned(node)
            if value is None:
                return node
            node = value
        return None
