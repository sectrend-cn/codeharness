"""Filter diagnostics by affected definitions without narrowing analysis evidence."""

from dataclasses import dataclass
from typing import Protocol

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import walk


class ScopeSyntax(Protocol):
    """Identify definition spans and the header of a class-like container."""

    def definition(self, node: Node) -> bool: ...
    def extent(self, node: Node) -> Node: ...
    def header_end(self, node: Node) -> int | None: ...


@dataclass(frozen=True)
class AffectedScopes:
    """Expand edited lines using grammar-owned definitions and module statements."""

    syntax: ScopeSyntax

    def lines(
        self, context: TreeContext, additional: frozenset[int] = frozenset()
    ) -> frozenset[int]:
        touched = context.source.changed_lines
        if touched is None:
            return frozenset(range(1, context.root.end_point.row + 2))
        touched = touched | additional
        selected = set(touched)
        for node in walk(context.root):
            if self._affected(node, touched, context.root):
                extent = self.syntax.extent(node)
                selected.update(range(extent.start_point.row + 1, extent.end_point.row + 2))
        return frozenset(selected)

    def includes(self, finding: Finding, lines: frozenset[int]) -> bool:
        """File placement and ownership remain obligations for every changed file."""
        return finding.scope == "file" or finding.line in lines

    def _affected(self, node: Node, touched: frozenset[int], root: Node) -> bool:
        extent = self.syntax.extent(node)
        start, end = extent.start_point.row + 1, extent.end_point.row + 1
        header = self.syntax.header_end(node)
        if header is not None:
            end = header
        elif not self.syntax.definition(node) and node.parent != root:
            return False
        return any(start <= line <= end for line in touched)
