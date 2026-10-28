"""Strict option contracts and checker-owned registration metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class Contract(BaseModel):
    """Reject unknown policy fields and preserve validated field types."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CheckerOptions(Contract):
    """Enable one logical checker and its associated diagnostics."""

    enabled: bool = True


@dataclass(frozen=True)
class CheckerDefinition:
    """Own a configuration key and the diagnostics governed by its switch."""

    name: str
    diagnostics: tuple[str, ...] = ()

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return self.diagnostics or (self.name,)

    def configure(self, enabled: bool) -> CheckerState:
        return CheckerState(self, enabled)


@dataclass(frozen=True)
class CheckerState:
    """Expose execution switches without carrying or erasing option payloads."""

    definition: CheckerDefinition
    enabled: bool


class CheckerConfiguration(Contract):
    """Compose checker registrations while each owner retains its concrete fields."""

    model_config = ConfigDict(populate_by_name=True)

    def checker_states(self) -> tuple[CheckerState, ...]:
        """Allow typed policy fragments to contribute through cooperative composition."""
        return ()

    @model_validator(mode="after")
    def validate_registrations(self) -> Self:
        names: set[str] = set()
        rules: set[str] = set()
        for state in self.checker_states():
            definition = state.definition
            if not definition.name or definition.name in names:
                raise ValueError(f"Duplicate or empty checker identity: {definition.name!r}")
            declared = definition.rule_ids
            if any(not rule for rule in declared) or len(set(declared)) != len(declared):
                raise ValueError(f"Invalid checker diagnostics: {definition.name}")
            if rules.intersection(declared):
                raise ValueError(f"Conflicting checker diagnostics: {definition.name}")
            names.add(definition.name)
            rules.update(declared)
        self._validate_fields(names)
        return self

    def _validate_fields(self, registered: set[str]) -> None:
        declared = {
            field.serialization_alias or name for name, field in type(self).model_fields.items()
        }
        if declared != registered:
            raise ValueError("Checker fields and registrations differ")

    def disabled_checkers(self) -> frozenset[str]:
        """Report logical configuration keys from their owner registrations."""
        return frozenset(
            state.definition.name for state in self.checker_states() if not state.enabled
        )

    def disabled_rules(self) -> frozenset[str]:
        """Expand disabled registrations without selecting individual checker names."""
        return frozenset(
            rule
            for state in self.checker_states()
            if not state.enabled
            for rule in state.definition.rule_ids
        )
