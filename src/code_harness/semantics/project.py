"""Connect explicitly imported declarations across the selected immutable snapshots."""

import posixpath

from code_harness.diagnostics import AnalysisError
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import ImportedName, UsageEvidence
from code_harness.semantics.overrides import OverrideUsage
from code_harness.semantics.parameter_properties import (
    ParameterPropertyIndex,
    ParameterPropertyUsage,
)


class ProjectUsage:
    """Resolve selected-file imports before evaluating unused declarations."""

    def __init__(self, indexes: tuple[SemanticIndex, ...]) -> None:
        self.indexes = indexes
        self.prepared = False
        self.modules: dict[str, SemanticIndex] = {}
        for index in indexes:
            for name in index.syntax.module_names(index.context):
                self.modules[name] = index

    def prepare(self) -> None:
        """Own project linking and reference refresh before rule evaluation."""
        if self.prepared:
            return
        snapshots = {index.context.root.id: index for index in self.indexes}
        for index in self.indexes:
            index.snapshot_indexes = snapshots
            self._connect(index)
            self._package(index)
        for index in self.indexes:
            index.refresh()
        for index in self.indexes:
            index.refresh()
        self.prepared = True

    def evidence(self) -> UsageEvidence:
        """Expose resolved facts without selecting or executing any rule policy."""
        if not self.prepared:
            raise AnalysisError("Project semantic evidence must be prepared before evaluation")
        contract_reads = (
            OverrideUsage(self.indexes).used_declarations().union(self._parameter_property_reads())
        )
        unresolved = frozenset(name for index in self.indexes for name in index.unresolved_reads)
        return UsageEvidence(unresolved, contract_reads)

    def _parameter_property_reads(self) -> frozenset[int]:
        syntaxes = tuple(index.syntax.parameter_property_syntax() for index in self.indexes)
        if not any(syntax is not None for syntax in syntaxes):
            return frozenset()
        indexes = tuple(
            ParameterPropertyIndex(index.context, syntax or index.syntax)
            for index, syntax in zip(self.indexes, syntaxes, strict=True)
        )
        ProjectUsage(indexes).prepare()
        return ParameterPropertyUsage(indexes).used_declarations()

    def _connect(self, index: SemanticIndex) -> None:
        for entry in index.syntax.imports(index.context):
            peer = self._module(index, entry)
            local = index.lookup(entry.name, index.locations.get(entry.node.id, 0))
            if peer is None or local is None or local.library:
                continue
            target = peer.scopes[0].symbols.get(entry.original or entry.name)
            if target is not None:
                local.target = target
                if target.kind == "class" and target.class_scope is not None:
                    index.imported_classes[entry.name] = target.class_scope
            else:
                local.class_scope = peer.scopes[0]
                for name, scope in peer.classes.items():
                    index.imported_classes[f"{entry.name}.{name}"] = peer.scopes[scope]

    def _package(self, index: SemanticIndex) -> None:
        package = index.syntax.package(index.context)
        if not package:
            return
        directory = posixpath.dirname(index.context.source.path)
        for peer in self.indexes:
            if peer is index or posixpath.dirname(peer.context.source.path) != directory:
                continue
            if peer.syntax.package(peer.context) != package:
                continue
            index.peer_symbols.update(peer.scopes[0].symbols)
            index.imported_classes.update(
                (name, peer.scopes[scope]) for name, scope in peer.classes.items()
            )

    def _module(self, index: SemanticIndex, entry: ImportedName) -> SemanticIndex | None:
        return self.modules.get(index.syntax.import_target(entry, index.context))
