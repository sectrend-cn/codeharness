"""Shared execution of language-owned type-marker checks."""

from dataclasses import dataclass
from typing import Protocol

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import walk
from code_harness.source import Source


class NodeRule(Protocol):
    """A syntax-node check retains concrete syntax and source contracts."""

    def issue(self, node: Node, source: Source) -> tuple[str, str] | None: ...


@dataclass(frozen=True)
class TypeMarkers:
    """Apply grammar-specific markers outside resolved outbound boundary spans."""

    context: TreeContext

    def check(self, rule: NodeRule) -> tuple[Finding, ...]:
        context = self.context
        findings: list[Finding] = []
        boundary = context.require_boundary()
        for node in walk(context.root):
            if boundary.contains(node):
                continue
            issue = rule.issue(node, context.source)
            if issue is not None:
                rule_id, message = issue
                findings.append(
                    Finding(
                        path=context.source.path,
                        line=node.start_point.row + 1,
                        column=node.start_point.column + 1,
                        rule=rule_id,
                        message=message,
                    )
                )
        return tuple(findings)
