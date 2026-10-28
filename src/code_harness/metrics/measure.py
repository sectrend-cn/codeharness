"""Grammar-independent calculations over typed syntax capabilities."""

from tree_sitter import Node

from code_harness.metrics.contracts import Metrics, MetricSyntax
from code_harness.source import Source


def _code_lines(root: Node, source: Source, semantics: MetricSyntax) -> frozenset[int]:
    """Count token-bearing physical lines, excluding comments and Python docstrings."""
    rows: set[int] = set()
    physical = source.content.splitlines()
    pending = [root]
    while pending:
        node = pending.pop()
        if semantics.ignored_line(node):
            continue
        if node.children:
            pending.extend(node.children)
            continue
        end = node.end_point.row + (node.end_point.column > 0)
        rows.update(row for row in range(node.start_point.row, end) if physical[row].strip())
    return frozenset(rows)


def _control_metrics(body: Node, source: Source, semantics: MetricSyntax) -> tuple[int, int, int]:
    complexity, nesting, statements = 1, 0, 0
    pending = [(body, 0)]
    while pending:
        node, depth = pending.pop()
        if semantics.is_function(node):
            continue
        next_depth = semantics.control_depth(node, depth)
        nesting = max(nesting, next_depth)
        complexity += semantics.decisions(node, source)
        statements += int(semantics.is_statement(node))
        pending.extend((child, next_depth) for child in node.named_children)
    return complexity, nesting, statements


def _measure(node: Node, source: Source, rows: frozenset[int], semantics: MetricSyntax) -> Metrics:
    """Include nested bodies in line spans but isolate their control-flow metrics."""
    body = semantics.body(node)
    complexity, nesting, statements = (1, 0, 0)
    if body is not None:
        complexity, nesting, statements = _control_metrics(body, source, semantics)
    lines = sum(node.start_point.row <= row <= node.end_point.row for row in rows)
    return Metrics(lines, statements, complexity, nesting, semantics.parameters(node, source))
