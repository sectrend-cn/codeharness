"""Canonical measurements and grammar interpretation consumed by metrics."""

from dataclasses import dataclass
from typing import Protocol

from tree_sitter import Node

from code_harness.source import Source


@dataclass(frozen=True)
class Metrics:
    """Independent bounds prevent line compression from hiding branch growth."""

    lines: int
    statements: int
    complexity: int
    nesting: int
    parameters: int


class MetricSyntax(Protocol):
    """Interpret only syntax needed for function measurements."""

    def is_function(self, node: Node) -> bool: ...
    def body(self, node: Node) -> Node | None: ...
    def ignored_line(self, node: Node) -> bool: ...
    def parameters(self, node: Node, source: Source) -> int: ...
    def control_depth(self, node: Node, depth: int) -> int: ...
    def decisions(self, node: Node, source: Source) -> int: ...
    def is_statement(self, node: Node) -> bool: ...
