"""Own exact snapshot trees and the single mutable semantic resolution phase."""

from dataclasses import dataclass

from code_harness.analysis.context import TreeContext
from code_harness.analysis.contracts import ContextParser
from code_harness.diagnostics import AnalysisError, SyntaxFailure
from code_harness.policy.models import Policy
from code_harness.semantics.boundaries import BoundaryEvidence
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import SemanticSyntax
from code_harness.semantics.project import ProjectUsage
from code_harness.source import Language, Source


@dataclass(frozen=True)
class SemanticBinding:
    """Bind a concrete parser and syntax capability at composition."""

    parser: ContextParser
    syntax: SemanticSyntax


class AnalysisSession:
    """Scope parse caches and mutable evidence to one immutable policy execution."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self._contexts: dict[tuple[Source, int], TreeContext] = {}
        self._project: ProjectUsage | None = None
        self._rejected: dict[tuple[Source, int], SyntaxFailure] = {}

    def context(self, source: Source, parser: ContextParser) -> TreeContext:
        """Include parser identity and exact bytes so grammar or content cannot alias."""
        key = source, id(parser)
        if key in self._rejected:
            raise self._rejected[key]
        if key not in self._contexts:
            self._contexts[key] = self._parse(source, parser)
        return self._contexts[key]

    def _parse(self, source: Source, parser: ContextParser) -> TreeContext:
        try:
            return parser.parse(source, self.policy)
        except SyntaxFailure as error:
            self._rejected[source, id(parser)] = error
            for warning in error.warnings:
                warning.emit()
            raise
        except AnalysisError:
            raise
        except Exception as error:
            raise AnalysisError(f"Parser failed for {source.path}: {error}") from error

    def prepare(
        self, sources: tuple[Source, ...], bindings: dict[Language, SemanticBinding]
    ) -> None:
        """Resolve the complete snapshot set before exposing evidence to any rule."""
        try:
            self._prepare(sources, bindings)
        except AnalysisError:
            raise
        except Exception as error:
            raise AnalysisError(f"Semantic preparation failed: {error}") from error

    def _prepare(
        self, sources: tuple[Source, ...], bindings: dict[Language, SemanticBinding]
    ) -> None:
        indexes: list[SemanticIndex] = []
        for source in dict.fromkeys(sources):
            binding = bindings.get(source.language)
            if binding is None:
                continue
            try:
                context = self.context(source, binding.parser)
            except SyntaxFailure:
                continue
            if context.semantic_index is None:
                context.semantic_index = SemanticIndex(context, binding.syntax)
            indexes.append(context.semantic_index)
        complete = tuple(index for index in indexes if not index.context.root.has_error)
        self._project = ProjectUsage(complete)
        self._project.prepare()
        for index in indexes:
            index.context.boundary_evidence = BoundaryEvidence(index)
        usage = self._project.evidence()
        for index in indexes:
            index.context.usage_evidence = usage
