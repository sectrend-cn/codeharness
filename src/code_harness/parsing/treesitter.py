"""Tree-sitter grammar selection and shared traversal operations."""

from collections.abc import Iterator
from dataclasses import dataclass

from tree_sitter import Language as Grammar
from tree_sitter import Node, Parser, Tree

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import ContextParser
from code_harness.diagnostics import ParseWarning
from code_harness.policy.models import Policy
from code_harness.source import Source


@dataclass(frozen=True)
class TreeParser(ContextParser):
    """Own a grammar and allocate a dedicated parser for each source snapshot."""

    grammar: Grammar

    def content(self, source: Source) -> bytes:
        return source.content

    def tree(self, source: Source) -> Tree:
        return Parser(self.grammar).parse(self.content(source))

    def parse(self, source: Source, policy: Policy) -> TreeContext:
        tree = self.tree(source)
        root = tree.root_node
        if root.has_error:
            for warning in self._rejections(root, source):
                warning.emit()
        return TreeContext(source, tree, policy)

    def _rejections(self, root: Node, source: Source) -> tuple[ParseWarning, ...]:
        warnings = tuple(
            ParseWarning(
                path=source.path,
                line=node.start_point.row + 1,
                column=node.start_point.column + 1,
                message=f"Parser rejected {node.type}; continuing checks on the recovered tree",
            )
            for node in walk(root)
            if node.is_error or node.is_missing
        )
        return warnings or (
            ParseWarning(
                path=source.path,
                line=1,
                column=1,
                message="Parser recovered from invalid syntax; continuing checks",
            ),
        )


def walk(root: Node) -> Iterator[Node]:
    """Visit every named syntax node without grammar-specific classification."""
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        children = node.named_children
        pending.extend(reversed(children))


def spelling(node: Node, source: Source) -> str:
    """Read exactly the UTF-8 bytes represented by a syntax node."""
    return source.content[node.start_byte : node.end_byte].decode("utf-8")


def field(node: Node, name: str) -> Node | None:
    """Expose the grammar's named-field lookup with its concrete optional result."""
    return node.child_by_field_name(name)
