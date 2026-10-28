"""Function metric checker options and diagnostic registration."""

from typing import ClassVar

from pydantic import Field

from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
)


class FunctionSizeOptions(CheckerOptions):
    """Own function metric limits and enable all five size diagnostics together."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "size.lines",
        "size.statements",
        "size.complexity",
        "size.nesting",
        "size.parameters",
    )
    lines: int = Field(default=50, ge=1)
    statements: int = Field(default=50, ge=1)
    complexity: int = Field(default=10, ge=1)
    nesting: int = Field(default=3, ge=1)
    parameters: int = Field(default=5, ge=1)


FUNCTION_SIZE = CheckerDefinition("function_size", FunctionSizeOptions.rule_ids)


class MetricCheckers(CheckerConfiguration):
    """Register owned checker fields and project their execution switches."""

    function_size: FunctionSizeOptions = Field(
        default=FunctionSizeOptions(),
        validation_alias=FUNCTION_SIZE.name,
        serialization_alias=FUNCTION_SIZE.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (
            *super().checker_states(),
            FUNCTION_SIZE.configure(self.function_size.enabled),
        )
