"""Grammar interpretation for qualified imports and transparent alias expressions."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.semantics.model import ImportedName


@dataclass(frozen=True)
class GrammarNames:
    """Parentheses preserve identity; other transformations need explicit interpretation."""

    builtins: frozenset[str] = frozenset()

    def transparent(self, node: Node) -> Node | None:
        if node.type == "parenthesized_expression" and node.named_child_count == 1:
            return node.named_children[0]
        return None

    def imported(self, entry: ImportedName) -> str:
        if not entry.original or entry.original == entry.module:
            return entry.module
        return f"{entry.module}.{entry.original}"

    def builtin(self, name: str) -> bool:
        return name in self.builtins
