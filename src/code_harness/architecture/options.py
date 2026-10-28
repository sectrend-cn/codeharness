"""Architecture checker contracts, options and registrations."""

from pydantic import Field

from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
    Contract,
)


class Boundary(Contract):
    """Forbid literal or normalized imports from matching source paths."""

    name: str = Field(min_length=1)
    sources: tuple[str, ...] = Field(min_length=1)
    forbidden_imports: tuple[str, ...] = Field(min_length=1)


class Owner(Contract):
    """Assign a named responsibility to repository-relative paths."""

    name: str = Field(min_length=1)
    paths: tuple[str, ...] = Field(min_length=1)


class SourcePlacement(Contract):
    """Keep explicitly selected source modules within their owning locations."""

    name: str = Field(min_length=1)
    paths: tuple[str, ...] = Field(min_length=1)
    allowed_paths: tuple[str, ...] = Field(min_length=1)


class StructureOptions(CheckerOptions):
    """Configure source placement independently of ownership and dependencies."""

    placements: tuple[SourcePlacement, ...] = ()


class OwnershipOptions(CheckerOptions):
    """Configure responsibility matching only for architecture.owner."""

    owners: tuple[Owner, ...] = ()


class ImportOptions(CheckerOptions):
    """Configure forbidden dependencies only for architecture.import."""

    boundaries: tuple[Boundary, ...] = ()


class ObjectModelOptions(CheckerOptions):
    """Select modules whose public extension behavior must belong to objects."""

    paths: tuple[str, ...] = ()


OWNERSHIP = CheckerDefinition("architecture.owner")

STRUCTURE = CheckerDefinition("architecture.structure")

IMPORTS = CheckerDefinition("architecture.import")

DISPATCH = CheckerDefinition("architecture.dispatch")

OBJECT_MODEL = CheckerDefinition("architecture.object_model")


class ArchitectureCheckers(CheckerConfiguration):
    """Register owned checker fields and project their execution switches."""

    architecture_owner: OwnershipOptions = Field(
        default=OwnershipOptions(),
        validation_alias=OWNERSHIP.name,
        serialization_alias=OWNERSHIP.name,
    )
    architecture_structure: StructureOptions = Field(
        default=StructureOptions(),
        validation_alias=STRUCTURE.name,
        serialization_alias=STRUCTURE.name,
    )
    architecture_import: ImportOptions = Field(
        default=ImportOptions(),
        validation_alias=IMPORTS.name,
        serialization_alias=IMPORTS.name,
    )
    architecture_dispatch: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=DISPATCH.name,
        serialization_alias=DISPATCH.name,
    )
    architecture_object_model: ObjectModelOptions = Field(
        default=ObjectModelOptions(),
        validation_alias=OBJECT_MODEL.name,
        serialization_alias=OBJECT_MODEL.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (
            *super().checker_states(),
            OWNERSHIP.configure(self.architecture_owner.enabled),
            STRUCTURE.configure(self.architecture_structure.enabled),
            IMPORTS.configure(self.architecture_import.enabled),
            DISPATCH.configure(self.architecture_dispatch.enabled),
            OBJECT_MODEL.configure(self.architecture_object_model.enabled),
        )
