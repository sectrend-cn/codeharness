"""Comment syntax shared by built-in tree-sitter grammars."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.parsing.treesitter import spelling, walk


class GrammarComments:
    """Expose comment tokens while grammar-specific adapters supply type markers."""

    requirements = RuleRequirements()

    def comments(self, root: Node) -> tuple[Node, ...]:
        return tuple(node for node in walk(root) if node.type == "comment")

    def disabled_types(self, context: TreeContext) -> tuple[Node, ...]:
        return ()


@dataclass(frozen=True)
class DirectiveSyntax:
    """Read standalone line-comment directives for one grammar's marker syntax."""

    node_types: frozenset[str]
    marker: str

    def candidates(self, context: TreeContext) -> tuple[Node, ...]:
        return tuple(
            node
            for node in walk(context.root)
            if node.type in self.node_types and "code-harness:" in spelling(node, context.source)
        )

    def directive_text(self, node: Node, context: TreeContext) -> str | None:
        text = spelling(node, context.source)
        line_start = context.source.content.rfind(b"\n", 0, node.start_byte) + 1
        prefix = context.source.content[line_start : node.start_byte]
        if not text.startswith(self.marker) or prefix.strip():
            return None
        return text[len(self.marker) :].strip()
