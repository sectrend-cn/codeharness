"""Shared consecutive-region policy for every registered projection syntax adapter."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import walk
from code_harness.semantics.projection.contracts import ProjectionSyntax
from code_harness.semantics.projection.matching import Projection, ProjectionMatcher
from code_harness.semantics.projection.options import GUARDED_PROJECTION


@dataclass(frozen=True)
class GuardedProjectionRule:
    """Report distinct destination fields without conflating complexity or separate regions."""

    syntax: ProjectionSyntax
    name: str = "builtin.guarded_projection"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements(semantic_evidence=True)
    rule_ids: tuple[str, ...] = GUARDED_PROJECTION.rule_ids

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        matcher = ProjectionMatcher(context.require_index(), self.syntax)
        return tuple(
            finding
            for region in walk(context.root)
            if self.syntax.region(region)
            for cluster in self._clusters(region, matcher)
            if len({entry.field for entry in cluster})
            >= context.policy.checkers.guarded_projection.min_fields
            for finding in (self._finding(cluster, context),)
        )

    def _clusters(
        self, region: Node, matcher: ProjectionMatcher
    ) -> tuple[tuple[Projection, ...], ...]:
        clusters: list[tuple[Projection, ...]] = []
        current: list[Projection] = []
        for node in region.named_children:
            if self.syntax.ignored(node):
                continue
            candidate = matcher.candidate(node, region)
            if current and (
                candidate is None
                or (candidate.source, candidate.destination)
                != (current[0].source, current[0].destination)
            ):
                clusters.append(tuple(current))
                current = []
            if candidate is not None:
                current.append(candidate)
        if current:
            clusters.append(tuple(current))
        return tuple(clusters)

    def _finding(self, cluster: tuple[Projection, ...], context: TreeContext) -> Finding:
        first = cluster[0]
        count = len({entry.field for entry in cluster})
        locations = ", ".join(
            f"{entry.node.start_point.row + 1}:{entry.node.start_point.column + 1}"
            for entry in cluster
        )
        predicates = ", ".join(sorted({entry.predicate for entry in cluster}))
        return Finding(
            path=context.source.path,
            line=first.node.start_point.row + 1,
            column=first.node.start_point.column + 1,
            rule=GUARDED_PROJECTION.name,
            message=(
                f"{count} guarded field projections from {first.source_name} into "
                f"{first.destination_name} (locations {locations}; predicates: {predicates}). "
                "Review the optional-field contract and use a concrete typed projection where "
                "appropriate; retain omission semantics. Replacing guards with conditional "
                "spreads does not resolve this pattern."
            ),
        )
