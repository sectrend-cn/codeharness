"""Mechanical evidence for class-based extension ownership and polymorphic dispatch."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.architecture.design_contracts import DesignSyntax
from code_harness.architecture.options import DISPATCH, OBJECT_MODEL
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import spelling, walk
from code_harness.policy.paths import matches
from code_harness.source import Source


@dataclass(frozen=True)
class ObjectDesignRule:
    """Reject identity switches and public procedural entry points in configured modules."""

    syntax: DesignSyntax
    name: str = "builtin.object_design"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements()
    rule_ids: tuple[str, ...] = (DISPATCH.name, OBJECT_MODEL.name)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        options = context.policy.checkers
        for node in walk(context.root):
            if options.architecture_dispatch.enabled and self.syntax.dispatch(node, context.source):
                findings.append(
                    self._finding(
                        context.source,
                        node,
                        DISPATCH.name,
                        "Use a registered interface implementation instead of identity dispatch",
                    )
                )
        if options.architecture_object_model.enabled and matches(
            context.source.path, options.architecture_object_model.paths
        ):
            findings.extend(self._procedural(context))
        return tuple(findings)

    def _procedural(self, context: TreeContext) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for function in self.syntax.module_functions(context.root):
            name = self.syntax.function_name(function)
            if name is not None and not spelling(name, context.source).startswith("_"):
                findings.append(
                    self._finding(
                        context.source,
                        function,
                        OBJECT_MODEL.name,
                        "Own extension behavior in a class implementing a narrow interface",
                    )
                )
        return tuple(findings)

    def _finding(self, source: Source, node: Node, rule: str, message: str) -> Finding:
        return Finding(
            path=source.path,
            line=node.start_point.row + 1,
            column=node.start_point.column + 1,
            rule=rule,
            message=message,
        )
