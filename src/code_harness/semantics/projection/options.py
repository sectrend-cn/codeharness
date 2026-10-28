"""Strict configuration owned by the guarded projection checker."""

from pydantic import Field

from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
)

GUARDED_PROJECTION = CheckerDefinition("structure.guarded_projection")


class GuardedProjectionOptions(CheckerOptions):
    """Count distinct destination fields within one consecutive local cluster."""

    min_fields: int = Field(default=3, ge=2)


class ProjectionCheckers(CheckerConfiguration):
    """Compose the checker schema and its diagnostic switch."""

    guarded_projection: GuardedProjectionOptions = Field(
        default=GuardedProjectionOptions(),
        validation_alias=GUARDED_PROJECTION.name,
        serialization_alias=GUARDED_PROJECTION.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (
            *super().checker_states(),
            GUARDED_PROJECTION.configure(self.guarded_projection.enabled),
        )
