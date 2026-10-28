"""Shared threshold policy for grammar-provided function syntax."""

from dataclasses import dataclass

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.metrics.contracts import MetricSyntax
from code_harness.metrics.measure import _code_lines, _measure
from code_harness.metrics.options import FUNCTION_SIZE
from code_harness.parsing.treesitter import walk


@dataclass(frozen=True)
class MetricRule:
    """Own threshold enforcement with injected language measurement semantics."""

    semantics: MetricSyntax
    name: str = "builtin.metrics"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements()
    rule_ids: tuple[str, ...] = FUNCTION_SIZE.rule_ids

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        root, source = context.root, context.source
        options = context.policy.checkers.function_size
        findings: list[Finding] = []
        rows = _code_lines(root, source, self.semantics)
        for node in walk(root):
            if not self.semantics.is_function(node) or self.semantics.body(node) is None:
                continue
            metrics = _measure(node, source, rows, self.semantics)
            dimensions = (
                ("lines", metrics.lines, options.lines),
                ("statements", metrics.statements, options.statements),
                ("complexity", metrics.complexity, options.complexity),
                ("nesting", metrics.nesting, options.nesting),
                ("parameters", metrics.parameters, options.parameters),
            )
            for name, actual, maximum in dimensions:
                if actual > maximum:
                    findings.append(
                        Finding(
                            path=source.path,
                            line=node.start_point.row + 1,
                            column=node.start_point.column + 1,
                            rule=f"size.{name}",
                            message=f"Function {name} is {actual}; maximum is {maximum}",
                        )
                    )
        return tuple(findings)
