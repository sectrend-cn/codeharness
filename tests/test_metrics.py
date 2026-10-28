"""Regression cases for honest cross-language measurement at policy boundaries."""

import pytest

from code_harness.engine import check
from code_harness.models import Language, Policy, Source
from code_harness.policy.models import (
    Checkers,
    FunctionSizeOptions,
)


@pytest.mark.parametrize("statements", [48, 49])
def test_exact_line_limit(statements: int) -> None:
    content = "function run() {\n" + "  work();\n" * statements + "}\n"
    findings = check(Source("app.js", content.encode(), Language.JAVASCRIPT), Policy())
    assert any(item.rule == "size.lines" for item in findings) == (statements == 49)


def test_python_assignments_are_not_double_counted() -> None:
    content = b"def run() -> int:\n    value = 1\n    return value\n"
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(statements=2)))
    assert check(Source("app.py", content, Language.PYTHON), policy) == ()


def test_elif_chain_is_not_nested_control_flow() -> None:
    content = (
        b"def run(value: int) -> int:\n"
        b"    if value == 1:\n        return 1\n"
        b"    elif value == 2:\n        return 2\n"
        b"    elif value == 3:\n        return 3\n"
        b"    return 0\n"
    )
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(nesting=1)))
    assert check(Source("app.py", content, Language.PYTHON), policy) == ()


def test_string_expression_in_control_block_is_not_a_docstring() -> None:
    content = (
        b"def run(value: bool) -> None:\n"
        b"    if value:\n"
        b"        '''first\n        second\n        third'''\n"
    )
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(lines=3)))
    findings = check(Source("app.py", content, Language.PYTHON), policy)
    assert any(item.rule == "size.lines" for item in findings)


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.GO, "package demo\ntype Payload interface{ /* rationale */ }"),
        (Language.TYPESCRIPT, "type Payload = { /* rationale */ };"),
    ],
)
def test_comments_do_not_hide_empty_contracts(language: Language, code: str) -> None:
    findings = check(Source("example", code.encode(), language), Policy())
    assert any(item.rule == "type.broad" for item in findings)


def test_short_circuit_conditions_count_toward_complexity() -> None:
    content = b"function run() { return first && second || third; }"
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(complexity=2)))
    findings = check(Source("app.js", content, Language.JAVASCRIPT), policy)
    assert any(item.rule == "size.complexity" for item in findings)
