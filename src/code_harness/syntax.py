"""Compatibility exports for the tree-sitter parsing boundary."""

from tree_sitter import Node, Tree

from code_harness.languages.metric_syntax import FUNCTIONS
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.plugins.builtins import tree_parser
from code_harness.source import Source


def parse(source: Source) -> Tree:
    """Parse a source snapshot with its declared grammar."""
    return tree_parser(source.language).tree(source)


__all__ = ["FUNCTIONS", "Node", "Tree", "field", "parse", "spelling", "walk"]
