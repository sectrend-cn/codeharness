"""Serialization checker configuration and exact output API contracts."""

from typing import Annotated, Self

from pydantic import Field, model_validator

from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
    Contract,
)

type ApiIdentity = Annotated[str, Field(min_length=1, pattern=r"^[^\s*?\[\]]+$")]
type ArgumentIndex = Annotated[int, Field(ge=0)]


class OutputApi(Contract):
    """Declare the exact payload positions of a project-approved output API."""

    call: ApiIdentity
    arguments: tuple[ArgumentIndex, ...] = ()
    keywords: tuple[
        Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")], ...
    ] = ()

    @model_validator(mode="after")
    def require_payload(self) -> Self:
        if not self.arguments and not self.keywords:
            raise ValueError("Output APIs require payload arguments or keywords")
        return self


class InstanceOutput(Contract):
    """Approve one source-owned instance member and its positional payloads."""

    path: Annotated[str, Field(min_length=1, pattern=r"^[^\s*?\[\]\\:]+$")]
    class_name: Annotated[str, Field(pattern=r"^[A-Za-z_$][A-Za-z0-9_$]*$")]
    member: Annotated[str, Field(pattern=r"^[A-Za-z_$][A-Za-z0-9_$]*$")]
    arguments: Annotated[tuple[ArgumentIndex, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_exact_path(self) -> Self:
        if any(part in {"", ".", ".."} for part in self.path.split("/")):
            raise ValueError("Instance outputs require a normalized repository-relative path")
        return self


class EncodingOptions(Contract):
    """Extend built-in serialization APIs without disabling their boundary checks."""

    encoders: tuple[ApiIdentity, ...] = ()
    decoders: tuple[ApiIdentity, ...] = ()
    outputs: tuple[OutputApi, ...] = ()
    instance_outputs: tuple[InstanceOutput, ...] = ()


class BroadTypeOptions(CheckerOptions):
    """Group encoding API configuration with the existing broad-type checker."""

    encoding: EncodingOptions = EncodingOptions()


BROAD_TYPE = CheckerDefinition("type.broad")


class EncodingCheckers(CheckerConfiguration):
    """Register owned checker fields and project their execution switches."""

    type_broad: BroadTypeOptions = Field(
        default=BroadTypeOptions(),
        validation_alias=BROAD_TYPE.name,
        serialization_alias=BROAD_TYPE.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (
            *super().checker_states(),
            BROAD_TYPE.configure(self.type_broad.enabled),
        )
