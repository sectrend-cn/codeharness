"""Class-owned source placement, ownership and dependency policy."""

from dataclasses import dataclass

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.architecture.imports import ImportExtractor, ImportResolver
from code_harness.architecture.models import Import
from code_harness.architecture.options import IMPORTS, OWNERSHIP, STRUCTURE, Boundary
from code_harness.diagnostics import Finding
from code_harness.policy.paths import matches
from code_harness.source import Source


@dataclass(frozen=True)
class ArchitectureRule:
    """Evaluate source placement, ownership and language-owned dependency boundaries."""

    extractor: ImportExtractor
    resolver: ImportResolver
    name: str = "builtin.architecture"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements()
    rule_ids: tuple[str, ...] = (
        OWNERSHIP.name,
        STRUCTURE.name,
        IMPORTS.name,
    )

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        source = context.source
        findings = [*self._ownership(context), *self._structure(context)]
        imports = context.policy.checkers.architecture_import
        if not imports.enabled:
            return tuple(findings)
        for dependency in self.extractor.extract(context):
            for boundary in imports.boundaries:
                if matches(source.path, boundary.sources) and self._forbidden(
                    dependency, source, boundary
                ):
                    findings.append(
                        Finding(
                            path=source.path,
                            line=dependency.line,
                            column=dependency.column,
                            rule=IMPORTS.name,
                            message=f"{boundary.name}: forbidden dependency {dependency.module}",
                        )
                    )
        return tuple(findings)

    def _structure(self, context: TreeContext) -> tuple[Finding, ...]:
        """Require selected files to live within their configured owner's locations."""
        source = context.source
        options = context.policy.checkers.architecture_structure
        if not options.enabled:
            return ()
        return tuple(
            Finding(
                path=source.path,
                line=1,
                column=1,
                rule=STRUCTURE.name,
                scope="file",
                message=(
                    f"{placement.name}: source must match an owning location: "
                    f"{', '.join(placement.allowed_paths)}"
                ),
            )
            for placement in options.placements
            if matches(source.path, placement.paths)
            and not matches(source.path, placement.allowed_paths)
        )

    def _ownership(self, context: TreeContext) -> tuple[Finding, ...]:
        source = context.source
        options = context.policy.checkers.architecture_owner
        if not options.enabled or not options.owners:
            return ()
        owners = [owner.name for owner in options.owners if matches(source.path, owner.paths)]
        if len(owners) == 1:
            return ()
        return (
            Finding(
                path=source.path,
                line=1,
                column=1,
                rule=OWNERSHIP.name,
                scope="file",
                message=f"Expected exactly one responsibility owner; found {len(owners)}",
            ),
        )

    def _forbidden(self, dependency: Import, source: Source, boundary: Boundary) -> bool:
        return any(
            matches(name, boundary.forbidden_imports)
            for name in self.resolver.names(dependency, source)
        )
