"""Boundary and usage checker registrations shared by language adapters."""

from pydantic import Field

from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
)

BOUNDARY = CheckerDefinition("type.boundary")

UNUSED_PARAMETER = CheckerDefinition("unused.parameter")

UNUSED_FUNCTION = CheckerDefinition("unused.function")

UNUSED_FIELD = CheckerDefinition("unused.field")

UNUSED_RETURN = CheckerDefinition("unused.return")

USAGE_RULES = (UNUSED_PARAMETER.name, UNUSED_FUNCTION.name, UNUSED_FIELD.name, UNUSED_RETURN.name)


class SemanticCheckers(CheckerConfiguration):
    """Register owned checker fields and project their execution switches."""

    type_boundary: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=BOUNDARY.name,
        serialization_alias=BOUNDARY.name,
    )
    unused_parameter: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=UNUSED_PARAMETER.name,
        serialization_alias=UNUSED_PARAMETER.name,
    )
    unused_function: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=UNUSED_FUNCTION.name,
        serialization_alias=UNUSED_FUNCTION.name,
    )
    unused_field: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=UNUSED_FIELD.name,
        serialization_alias=UNUSED_FIELD.name,
    )
    unused_return: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=UNUSED_RETURN.name,
        serialization_alias=UNUSED_RETURN.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (
            *super().checker_states(),
            BOUNDARY.configure(self.type_boundary.enabled),
            UNUSED_PARAMETER.configure(self.unused_parameter.enabled),
            UNUSED_FUNCTION.configure(self.unused_function.enabled),
            UNUSED_FIELD.configure(self.unused_field.enabled),
            UNUSED_RETURN.configure(self.unused_return.enabled),
        )
