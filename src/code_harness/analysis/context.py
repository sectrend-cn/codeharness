"""One tree-backed context and its session-owned semantic evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tree_sitter import Node, Tree

from code_harness.diagnostics import AnalysisError
from code_harness.policy.models import Policy
from code_harness.source import Source

if TYPE_CHECKING:
    from code_harness.semantics.boundaries import BoundaryEvidence
    from code_harness.semantics.index import SemanticIndex
    from code_harness.semantics.model import UsageEvidence


@dataclass
class TreeContext:
    """Retain an exact source tree and evidence prepared before rule execution."""

    source: Source
    tree: Tree
    policy: Policy
    semantic_index: SemanticIndex | None = None
    boundary_evidence: BoundaryEvidence | None = None
    usage_evidence: UsageEvidence | None = None

    @property
    def root(self) -> Node:
        return self.tree.root_node

    def require_index(self) -> SemanticIndex:
        """Reject rule composition without the required semantic capability."""
        if self.semantic_index is None:
            raise AnalysisError("Semantic evidence was not prepared for this rule")
        return self.semantic_index

    def require_boundary(self) -> BoundaryEvidence:
        """Expose boundary evidence after its session-owned resolution phase."""
        if self.boundary_evidence is None:
            raise AnalysisError("Boundary evidence was not prepared for this rule")
        return self.boundary_evidence

    def require_usage(self) -> UsageEvidence:
        """Expose prepared project-wide usage evidence to registered usage rules."""
        if self.usage_evidence is None:
            raise AnalysisError("Usage evidence was not prepared for this rule")
        return self.usage_evidence
