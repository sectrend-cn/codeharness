"""Behavioral acceptance and rejection examples for every supported grammar."""

import pytest

from code_harness.engine import check
from code_harness.models import Boundary, Language, Owner, Policy, Source
from code_harness.policy.models import (
    Checkers,
    FunctionSizeOptions,
    ImportOptions,
    OwnershipOptions,
)

_DEFAULT_POLICY = Policy()


def _rules(code: str, language: Language, policy: Policy = _DEFAULT_POLICY) -> set[str]:
    source = Source("src/domain/example.py", code.encode(), language)
    return {finding.rule for finding in check(source, policy)}


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def total(value: int) -> int:\n    return value + 1\n"),
        (Language.GO, "package demo\nfunc Total(value int) int { return value + 1 }"),
        (Language.JAVASCRIPT, "export const total = (value) => value + 1;"),
        (Language.TYPESCRIPT, "export const total = (value: number): number => value + 1;"),
        (Language.TSX, "export const Total = () => <div>total</div>;"),
    ],
)
def test_concrete_programs_pass(language: Language, code: str) -> None:
    assert _rules(code, language) == set()


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def broken(:\n"),
        (Language.GO, "package demo\nfunc broken( {"),
        (Language.JAVASCRIPT, "function broken( {"),
        (Language.TYPESCRIPT, "const broken: = ;"),
        (Language.TSX, "const broken = <div>;"),
    ],
)
def test_parse_recovery_warns_without_a_defect(
    language: Language, code: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert _rules(code, language) == set()
    assert "syntax warning" in caplog.text
    assert "analysis results may be inaccurate" in caplog.text


@pytest.mark.parametrize(
    "code",
    [
        "from typing import Any as Payload\ndef run(value: Payload) -> int:\n    return 1",
        "import typing as contracts\ndef run(value: contracts.Any) -> int:\n    return 1",
        "def run(value: 'dict[str, object]') -> int:\n    return 1",
        "def run(value: list) -> int:\n    return 1",
        "from typing import Callable\ncallback: Callable[..., int]",
        "type Payload = dict[str, object]",
    ],
)
def test_python_rejects_erased_contracts(code: str) -> None:
    assert "type.annotation" in _rules(code, Language.PYTHON)


def test_python_requires_signatures_and_detects_aliased_casts() -> None:
    code = "from typing import cast as pretend\ndef run(value):\n    return pretend(int, value)"
    assert {"type.signature", "type.assertion"} <= _rules(code, Language.PYTHON)


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.GO, "package demo\ntype Payload interface{}"),
        (Language.GO, "package demo\ntype Payload = map[string]any"),
        (Language.TYPESCRIPT, "type Payload = any;"),
        (Language.TYPESCRIPT, "type Payload = unknown;"),
        (Language.TYPESCRIPT, "type Payload = object;"),
        (Language.TYPESCRIPT, "type Payload = {};"),
    ],
)
def test_broad_go_and_typescript_contracts_fail(language: Language, code: str) -> None:
    assert "type.broad" in _rules(code, language)


@pytest.mark.parametrize(
    "code",
    [
        "const result = payload as Result;",
        "const result = <Result>payload;",
        "const result = payload!;",
    ],
)
def test_typescript_assertions_fail(code: str) -> None:
    assert "type.assertion" in _rules(code, Language.TYPESCRIPT)


def test_typescript_checked_satisfies_and_const_are_supported() -> None:
    assert (
        _rules("const value = {kind: 'ok'} as const satisfies Result;", Language.TYPESCRIPT)
        == set()
    )


@pytest.mark.parametrize(
    ("language", "comment"),
    [
        (Language.PYTHON, "# type: ignore"),
        (Language.PYTHON, "# noqa: ANN401"),
        (Language.GO, "package demo\n//nolint:all"),
        (Language.JAVASCRIPT, "// eslint-disable-next-line"),
        (Language.TYPESCRIPT, "// @ts-ignore"),
        (Language.TYPESCRIPT, "// @ts-nocheck"),
    ],
)
def test_source_suppressions_are_not_an_escape_hatch(language: Language, comment: str) -> None:
    assert "type.suppression" in _rules(comment, language)


def test_strings_and_literal_annotation_values_are_not_code() -> None:
    python = "from typing import Literal\nvalue: Literal['Any'] = 'Any'\ntext = '# type: ignore'"
    assert _rules(python, Language.PYTHON) == set()
    assert _rules('const message = "any as Result // @ts-ignore";', Language.TYPESCRIPT) == set()


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "def run(a: int, b: int, c: int, d: int, e: int, f: int) -> int:\n return a",
        ),
        (Language.GO, "package demo\nfunc Run(a, b, c, d, e, f int) int { return a }"),
        (Language.JAVASCRIPT, "const run = (a, b, c, d, e, f) => a;"),
        (Language.TYPESCRIPT, "class App { constructor(a: A, b: B, c: C, d: D, e: E, f: F) {} }"),
    ],
)
def test_six_parameters_fail(language: Language, code: str) -> None:
    assert "size.parameters" in _rules(code, language)


def test_nested_callbacks_receive_their_own_complexity_check() -> None:
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(complexity=2)))
    source = Source(
        "app.js", b"function outer() { return () => { if (x) {} if (y) {} }; }", Language.JAVASCRIPT
    )
    findings = [finding for finding in check(source, policy) if finding.rule == "size.complexity"]
    assert len(findings) == 1
    assert findings[0].column > 1


def test_nested_bodies_still_count_toward_outer_line_limit() -> None:
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(lines=3)))
    code = "function outer() {\n return () => {\n  run();\n };\n}"
    assert "size.lines" in _rules(code, Language.JAVASCRIPT, policy)


def test_comment_lines_do_not_inflate_function_size() -> None:
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(lines=2)))
    code = "def run() -> int:\n    '''Purpose.'''\n    # explanation\n\n    return 1"
    assert _rules(code, Language.PYTHON, policy) == set()


def test_compressed_statements_cannot_bypass_metrics() -> None:
    policy = Policy(checkers=Checkers(function_size=FunctionSizeOptions(statements=2)))
    assert "size.statements" in _rules(
        "function run() { one(); two(); three(); }", Language.JAVASCRIPT, policy
    )


@pytest.mark.parametrize(
    ("language", "code", "forbidden"),
    [
        (Language.PYTHON, "from adapters.storage import Store", "adapters.*"),
        (Language.PYTHON, "from ..adapters import storage", "src.adapters.*"),
        (
            Language.GO,
            'package demo\nimport "example.com/app/adapters"',
            "example.com/app/adapters",
        ),
        (Language.JAVASCRIPT, 'const store = require("../adapters/store.js");', "src/adapters/*"),
        (Language.JAVASCRIPT, 'const store = import("../adapters/store.js");', "src/adapters/*"),
        (Language.TYPESCRIPT, 'import type {Store} from "../adapters/store.js";', "src/adapters/*"),
        (Language.TYPESCRIPT, 'export type {Store} from "../adapters/store.js";', "src/adapters/*"),
    ],
)
def test_architecture_rejects_visible_dependencies(
    language: Language,
    code: str,
    forbidden: str,
) -> None:
    policy = Policy(
        checkers=Checkers(
            architecture_import=ImportOptions(
                boundaries=(
                    Boundary(
                        name="domain", sources=("src/domain/*",), forbidden_imports=(forbidden,)
                    ),
                )
            )
        )
    )
    assert "architecture.import" in _rules(code, language, policy)


def test_file_ownership_requires_exactly_one_match() -> None:
    owner = Owner(name="domain", paths=("src/domain/*",))
    assert (
        _rules(
            "",
            Language.PYTHON,
            Policy(checkers=Checkers(architecture_owner=OwnershipOptions(owners=(owner,)))),
        )
        == set()
    )
    assert "architecture.owner" in _rules(
        "",
        Language.PYTHON,
        Policy(checkers=Checkers(architecture_owner=OwnershipOptions(owners=(owner, owner)))),
    )
    assert "architecture.owner" in _rules(
        "",
        Language.PYTHON,
        Policy(
            checkers=Checkers(
                architecture_owner=OwnershipOptions(
                    owners=(Owner(name="other", paths=("other/*",)),)
                )
            )
        ),
    )
