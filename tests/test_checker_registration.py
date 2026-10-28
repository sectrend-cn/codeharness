"""Checker owners compose strict typed schemas and diagnostic switches once."""

import pytest
from pydantic import Field, ValidationError

from code_harness.plugins.builtins import builtin_analyzers
from code_harness.policy.contracts import (
    CheckerConfiguration,
    CheckerDefinition,
    CheckerOptions,
    CheckerState,
)
from code_harness.policy.models import Checkers, Policy

_EXTENSION = CheckerDefinition("project.module_size", ("module.lines", "module.statements"))


class _ModuleOptions(CheckerOptions):
    """Configure a separate module-wide measurement policy."""

    maximum: int = Field(default=100, ge=1)


class _ModuleCheckers(CheckerConfiguration):
    """Contribute one concrete schema and its switch without editing the aggregate."""

    module_size: _ModuleOptions = Field(
        default=_ModuleOptions(),
        validation_alias=_EXTENSION.name,
        serialization_alias=_EXTENSION.name,
    )

    def checker_states(self) -> tuple[CheckerState, ...]:
        return (*super().checker_states(), _EXTENSION.configure(self.module_size.enabled))


class _ExtendedCheckers(_ModuleCheckers, Checkers):
    """Explicitly compose project configuration with built-in configuration."""


class _ExtendedPolicy(Policy):
    checkers: _ExtendedCheckers = _ExtendedCheckers()


class _RegistrationProbe(CheckerConfiguration):
    """Exercise invalid registration compositions independently of rule execution."""

    definitions: tuple[CheckerDefinition, ...]

    def checker_states(self) -> tuple[CheckerState, ...]:
        return tuple(definition.configure(True) for definition in self.definitions)


def test_custom_checker_contributes_typed_options_and_grouped_switch() -> None:
    policy = _ExtendedPolicy.model_validate_json(
        '{"checkers":{"project.module_size":{"enabled":false,"maximum":12},'
        '"function_size":{"complexity":2}}}'
    )
    assert policy.checkers.module_size.maximum == 12
    assert policy.checkers.function_size.complexity == 2
    assert policy.checkers.type_broad.encoding.encoders == ()
    assert policy.checkers.disabled_checkers() == {_EXTENSION.name}
    assert policy.checkers.disabled_rules() == {"module.lines", "module.statements"}
    assert _ExtendedPolicy().checkers.disabled_rules() == frozenset()
    assert Policy().checkers.disabled_rules() == frozenset()


@pytest.mark.parametrize(
    "options",
    ['{"maximum":0}', '{"maximum":true}', '{"maximum":"12"}', '{"unknown":1}', "null"],
)
def test_custom_schema_rejects_invalid_options_even_when_disabled(options: str) -> None:
    with pytest.raises(ValidationError):
        _ExtendedPolicy.model_validate_json('{"checkers":{"project.module_size":' + options + "}}")
    if options != "null":
        with pytest.raises(ValidationError):
            _ExtendedPolicy.model_validate_json(
                '{"checkers":{"project.module_size":{"enabled":false,' + options[1:] + "}}"
            )


def test_custom_checker_requires_explicit_composition() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Policy.model_validate_json('{"checkers":{"project.module_size":{}}}')


def test_python_construction_preserves_concrete_options_and_existing_aliases() -> None:
    options = _ModuleOptions(enabled=False, maximum=24)
    checkers = _ExtendedCheckers(module_size=options)
    policy = _ExtendedPolicy(checkers=checkers)
    assert policy.checkers.module_size is options
    assert policy.checkers.disabled_rules() == frozenset(_EXTENSION.rule_ids)
    assert checkers.disabled_rules() == policy.checkers.disabled_rules()
    assert '"project.module_size"' in policy.model_dump_json(by_alias=True)
    assert '"module_size"' not in policy.model_dump_json(by_alias=True)


def test_registered_diagnostics_match_all_builtin_analyzer_coverage() -> None:
    configured = {
        rule for state in Checkers().checker_states() for rule in state.definition.rule_ids
    }
    executed = {rule for analyzer in builtin_analyzers() for rule in analyzer.rule_ids}
    assert configured == executed
    assert len(Checkers().checker_states()) == 18
    assert {state.definition.name for state in Checkers().checker_states()} == {
        field.serialization_alias or name for name, field in Checkers.model_fields.items()
    }


@pytest.mark.parametrize("definition", [state.definition for state in Checkers().checker_states()])
def test_every_registered_switch_expands_its_declared_rules(definition: CheckerDefinition) -> None:
    policy = Policy.model_validate_json(
        '{"checkers":{"' + definition.name + '":{"enabled":false}}}'
    )
    assert policy.checkers.disabled_checkers() == {definition.name}
    assert policy.checkers.disabled_rules() == frozenset(definition.rule_ids)


@pytest.mark.parametrize(
    ("definitions", "message"),
    [
        ((CheckerDefinition(""),), "empty checker identity"),
        ((CheckerDefinition("one"), CheckerDefinition("one")), "Duplicate"),
        ((CheckerDefinition("one", ("",)),), "Invalid checker diagnostics"),
        ((CheckerDefinition("one", ("rule", "rule")),), "Invalid checker diagnostics"),
        (
            (CheckerDefinition("one", ("rule",)), CheckerDefinition("two", ("rule",))),
            "Conflicting checker diagnostics",
        ),
    ],
)
def test_invalid_registration_fails_closed(
    definitions: tuple[CheckerDefinition, ...], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _RegistrationProbe(definitions=definitions)


class _UnregisteredCheckers(Checkers):
    """Demonstrate that adding a schema field alone cannot silently bypass reporting."""

    orphan: CheckerOptions = CheckerOptions()


def test_unregistered_options_fail_closed() -> None:
    with pytest.raises(ValidationError, match="Checker fields and registrations differ"):
        _UnregisteredCheckers()


def test_package_rule_exports_remain_available() -> None:
    from code_harness.architecture import ArchitectureRule
    from code_harness.architecture.rules import ArchitectureRule as CanonicalArchitectureRule
    from code_harness.metrics import MetricRule
    from code_harness.metrics.rules import MetricRule as CanonicalMetricRule

    assert ArchitectureRule is CanonicalArchitectureRule
    assert MetricRule is CanonicalMetricRule


def test_lazy_package_exports_reject_unknown_names() -> None:
    from code_harness.architecture import __getattr__ as architecture_export
    from code_harness.metrics import __getattr__ as metrics_export

    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        assert architecture_export("missing").__name__ == "missing"
    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        assert metrics_export("missing").__name__ == "missing"
