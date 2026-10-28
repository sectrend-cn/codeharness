"""Type and syntax checker switches shared across language implementations."""

from pydantic import Field

from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
)

ANNOTATION = CheckerDefinition("type.annotation")

SIGNATURE = CheckerDefinition("type.signature")

ASSERTION = CheckerDefinition("type.assertion")

SUPPRESSION = CheckerDefinition("type.suppression")

WILDCARD = CheckerDefinition("imports.wildcard")


class TypeCheckers(CheckerConfiguration):
    """Register owned checker fields and project their execution switches."""

    type_annotation: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=ANNOTATION.name,
        serialization_alias=ANNOTATION.name,
    )
    type_signature: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=SIGNATURE.name,
        serialization_alias=SIGNATURE.name,
    )
    type_assertion: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=ASSERTION.name,
        serialization_alias=ASSERTION.name,
    )
    type_suppression: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=SUPPRESSION.name,
        serialization_alias=SUPPRESSION.name,
    )
    imports_wildcard: CheckerOptions = Field(
        default=CheckerOptions(),
        validation_alias=WILDCARD.name,
        serialization_alias=WILDCARD.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (
            *super().checker_states(),
            ANNOTATION.configure(self.type_annotation.enabled),
            SIGNATURE.configure(self.type_signature.enabled),
            ASSERTION.configure(self.type_assertion.enabled),
            SUPPRESSION.configure(self.type_suppression.enabled),
            WILDCARD.configure(self.imports_wildcard.enabled),
        )
