"""Python annotation and recovery contracts on the common tree-sitter context."""

import pytest

from code_harness.diagnostics import Finding
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _findings(code: str) -> tuple[Finding, ...]:
    return check(Source("app.py", code.encode("utf-8"), Language.PYTHON), Policy())


@pytest.mark.parametrize(
    "annotation",
    [
        '"\\x41ny"',
        '"\\u0041ny"',
        '"dict[str, " "object]"',
        'list["object"]',
        '"list[\\"object\\"]"',
        '"dict[str, object]"',
        'r"dict[str, object]"',
        '"""dict[str, object]"""',
        '"Annotated[object, 1]"',
        '"Callable[..., int]"',
    ],
)
def test_forward_annotation_forms_preserve_contract_checks(annotation: str) -> None:
    findings = _findings(f"value: {annotation}\n")
    annotations = tuple(finding for finding in findings if finding.rule == "type.annotation")
    assert len(annotations) == 1
    assert annotations[0].line == 1
    assert annotations[0].column == 8


@pytest.mark.parametrize(
    "annotation",
    [
        'Literal["Any"]',
        'Annotated[int, "object"]',
        '"Literal[\\"Any\\"]"',
        '"Annotated[int, \\"object\\"]"',
        'dict[str, "用户"]',
        '"Callable[[int, str], bool]"',
    ],
)
def test_annotation_values_and_concrete_forward_types_are_not_erasure(annotation: str) -> None:
    assert not any(
        finding.rule == "type.annotation" for finding in _findings(f"value: {annotation}")
    )


@pytest.mark.parametrize("annotation", ['"list["', '"x = 1"', '"int; str"', '""'])
def test_invalid_forward_annotations_are_reported(annotation: str) -> None:
    annotations = tuple(
        finding
        for finding in _findings(f"value: {annotation}")
        if finding.rule == "type.annotation"
    )
    assert len(annotations) == 1
    assert annotations[0].message == "Invalid forward type annotation"


def test_async_signature_preserves_parameter_order_and_receiver_exemption() -> None:
    code = "async def run(self, first, /, second=1, *args, third, **kwargs):\n    pass\n"
    signatures = tuple(finding for finding in _findings(code) if finding.rule == "type.signature")
    assert len(signatures) == 1
    assert signatures[0].message == (
        "Declare concrete interface types: first, second, third, args, kwargs, return"
    )
    assert (signatures[0].line, signatures[0].column) == (1, 1)


def test_annotation_and_escape_locations_use_utf8_columns() -> None:
    code = "from typing import Any as Payload\n名字: Payload = None\n"
    findings = tuple(
        finding for finding in _findings(code) if finding.rule in {"type.annotation", "type.broad"}
    )
    assert {(finding.rule, finding.line, finding.column) for finding in findings} == {
        ("type.annotation", 2, 9),
        ("type.broad", 2, 9),
    }


def test_recovered_python_keeps_independent_annotation_checks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    findings = _findings("value: object = None\ndef broken(:\n")
    assert any(finding.rule == "type.annotation" and finding.line == 1 for finding in findings)
    assert "syntax warning" in caplog.text


def test_type_comments_do_not_disable_python_tree_checks() -> None:
    findings = _findings("value: object = None # type: object\n")
    assert any(finding.rule == "type.annotation" for finding in findings)


def test_parenthesized_annotation_reports_inner_expression_location() -> None:
    annotations = tuple(
        finding for finding in _findings("value: (object)") if finding.rule == "type.annotation"
    )
    assert len(annotations) == 1
    assert annotations[0].column == 9


def test_forward_comments_and_interpolated_annotations_preserve_checks() -> None:
    code = 'first: "# comment\\nobject"\nsecond: f"{object}"\n'
    assert {finding.line for finding in _findings(code) if finding.rule == "type.annotation"} == {
        1,
        2,
    }
