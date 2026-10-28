"""Constructor properties retain declaration identity across member reads."""

from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Finding, Report
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _unused(code: str, language: Language = Language.TYPESCRIPT) -> tuple[Finding, ...]:
    findings = check(Source("sample.ts", code.encode(), language), Policy())
    return tuple(f for f in findings if f.rule in {"unused.parameter", "unused.field"})


@pytest.mark.parametrize("language", [Language.TYPESCRIPT, Language.TSX])
@pytest.mark.parametrize(
    "modifier",
    [
        "public",
        "protected",
        "private",
        "readonly",
        "public readonly",
        "protected readonly",
        "private readonly",
    ],
)
def test_this_read_uses_parameter_property(language: Language, modifier: str) -> None:
    code = (
        f"export class Item {{ constructor({modifier} value: number) {{}} "
        "read(): number { return this.value; } }"
    )
    assert _unused(code, language) == ()


@pytest.mark.parametrize("declaration", ["value: number", "value: number = 1", "value?: number"])
def test_unread_property_retains_parameter_diagnostic(declaration: str) -> None:
    code = f"export class Item {{ constructor(public {declaration}) {{}} }}"
    findings = _unused(code)
    assert len(findings) == 1
    assert findings[0].rule == "unused.parameter"
    assert findings[0].column == code.index("value") + 1


@pytest.mark.parametrize(
    "body", ["this.value = 2;", "value = 2;", "const item = {value: 2}; console.log(item.value);"]
)
def test_writes_and_unrelated_object_reads_do_not_use_property(body: str) -> None:
    code = f"export class Item {{ constructor(public value: number = 1) {{ {body} }} }}"
    findings = tuple(f for f in _unused(code) if f.rule == "unused.parameter")
    assert len(findings) == 1
    assert findings[0].rule == "unused.parameter"


@pytest.mark.parametrize(
    "use",
    [
        "console.log(new Item(1).value);",
        "const item = new Item(1); console.log(item.value);",
        "export function read(item: Item): number { return item.value; }",
        "export class Child extends Item { read(): number { return this.value; } }",
    ],
)
def test_external_and_inherited_reads_use_property(use: str) -> None:
    code = "export class Item { constructor(public value: number) {} } " + use
    assert _unused(code) == ()


@pytest.mark.parametrize(
    "code",
    [
        "export class Box<T> { constructor(readonly value: T) {} "
        "read(): T { return this.value; } }",
        "export class Box<T> { constructor(readonly value: T) {} } "
        "export function read(box: Box<number>): number { return box.value; }",
        "export class Item { constructor(readonly value: number = 1) {} "
        "read(): number { return this.value; } }",
        "export class Item { constructor(readonly value?: number) {} "
        "read(): number | undefined { return this.value; } }",
        "export class State { record(): number { return 1; } } "
        "export class Item { constructor(private readonly state: State = new State()) {} "
        "read(): number { return this.state.record(); } }",
    ],
)
def test_generic_optional_and_default_properties(code: str) -> None:
    assert _unused(code) == ()


@pytest.mark.parametrize("body", ["console.log(value);", "const read = () => value; read();"])
def test_lexical_reads_still_use_parameter(body: str) -> None:
    code = f"export class Item {{ constructor(private value: number) {{ {body} }} }}"
    assert _unused(code) == ()


@pytest.mark.parametrize(
    "body",
    [
        "{ const value = 1; console.log(value); }",
        "function read(value: number): number { return value; } console.log(read(1));",
    ],
)
def test_shadowed_parameter_does_not_use_property(body: str) -> None:
    code = f"export class Item {{ constructor(private value: number) {{ {body} }} }}"
    findings = _unused(code)
    assert len(findings) == 1
    assert findings[0].column == code.index("value") + 1


@pytest.mark.parametrize("member", ["value = 1;", "constructor(public value: number) {}"])
def test_unrelated_same_named_members_do_not_use_property(member: str) -> None:
    code = (
        "export class Unread { constructor(public value: number) {} }\n"
        f"export class Read {{ {member} read(): number {{ return this.value; }} }}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 1)


def test_nested_same_named_class_keeps_property_identity() -> None:
    code = (
        "export class Item { constructor(public value: number) {} }\n"
        "export function read(): number {\n"
        "  class Item { constructor(public value: number) {} }\n"
        "  const item = new Item(1); return item.value;\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 1)


def test_child_property_does_not_use_shadowed_base_property() -> None:
    code = (
        "export class Base { constructor(public value: number) {} }\n"
        "export class Child extends Base { value = 2; read(): number { return this.value; } }"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 1)


def test_method_parameter_is_distinct_from_property_read() -> None:
    code = (
        "export class Item {\n"
        "  constructor(private readonly value: number) {}\n"
        "  read(value: number): number { return this.value; }\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 3)


def test_ordinary_constructor_parameter_is_not_a_property() -> None:
    code = (
        "export class Item {\n"
        "  value = 1;\n"
        "  constructor(value: number) {}\n"
        "  read(): number { return this.value; }\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 3)


@pytest.mark.parametrize(
    "consumer",
    [
        'import {Used} from "./models"; '
        "export function read(item: Used<number>): number { return item.value; }",
        'import {Used as Base} from "./models"; '
        "export class Child extends Base<number> { read(): number { return this.value; } }",
    ],
)
def test_cross_file_reads_preserve_occurrence_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], consumer: str
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "models.ts").write_text(
        "export class Used<T> { constructor(public readonly value: T) {} }\n"
        "export class Unread<T> { constructor(public readonly value: T) {} }\n"
    )
    (tmp_path / "consumer.ts").write_text(consumer)
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.rule, f.line, f.column) for f in report.findings] == [
        ("models.ts", "unused.parameter", 2, 54)
    ]


def test_bare_outer_variable_does_not_read_instance_property() -> None:
    code = (
        "const value = 1;\n"
        "export class Item {\n"
        "  constructor(private value: number) {}\n"
        "  read(): number { return value; }\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 3)


def test_shadowed_base_class_retains_inherited_property_identity() -> None:
    code = (
        "export class Base { constructor(public value: number) {} }\n"
        "export function read(): number {\n"
        "  class Base { constructor(public value: number) {} }\n"
        "  class Child extends Base { read(): number { return this.value; } }\n"
        "  return new Child(1).read();\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 1)


@pytest.mark.parametrize("generic", ["", "<T>"])
def test_abstract_class_parameter_property_is_used(generic: str) -> None:
    code = (
        f"export abstract class Base{generic} {{ constructor(protected value: number) {{}} "
        "read(): number { return this.value; } }"
    )
    assert _unused(code) == ()


def test_outer_base_is_not_replaced_by_later_nested_class() -> None:
    code = (
        "export class Base { constructor(public value: number) {} }\n"
        "export class Child extends Base { read(): number { return this.value; } }\n"
        "export function nested() {\n"
        "  class Base { constructor(public value: number) {} }\n"
        "  return Base;\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 4)


def test_instanceof_read_uses_resolved_parameter_property() -> None:
    code = (
        "export class Value extends Error { constructor(readonly text: string) { super(); } }\n"
        "export class Other { constructor(readonly text: string) {} }\n"
        "export function read(value: Error): string {\n"
        "  return value instanceof Value ? value.text : value.message;\n"
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 2)


def test_guarded_ternary_initializer_preserves_property_owner() -> None:
    code = (
        "export class Failure extends Error {\n"
        "  constructor(readonly status: number) { super(); }\n"
        "}\n"
        "export function read(): number {\n"
        "  try { throw new Error(); } catch (error) {\n"
        "    const failure = error instanceof Failure ? error : new Failure(503);\n"
        "    return failure.status;\n"
        "  }\n"
        "}"
    )
    assert _unused(code) == ()


@pytest.mark.parametrize(
    "body",
    [
        'return value instanceof Value ? "present" : value.text;',
        'if (value instanceof Value) { value = new Error(); return value.text; } return "";',
        'if (value instanceof Value) { const value = {text: "local"}; '
        'return value.text; } return "";',
        "if (value instanceof Value) { function read(value: Error) { return value.text; } "
        'return read(value); } return "";',
    ],
)
def test_guard_must_cover_the_same_unmodified_receiver(body: str) -> None:
    code = (
        "export class Value extends Error { constructor(readonly text: string) { super(); } }\n"
        f"export function read(value: Error): string {{ {body} }}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 1)


def test_read_after_property_write_still_counts() -> None:
    code = (
        "export class Item { constructor(public value: number) { this.value = 2; } "
        "read(): number { return this.value; } }"
    )
    assert _unused(code) == ()


def test_property_reads_do_not_change_return_diagnostics() -> None:
    code = (
        "export class State { read(): number { return 1; } }\n"
        "export class Item { constructor(private state: State) {} "
        "run(): void { this.state.read(); } }\n"
        "function value(): number { return 1; } value();"
    )
    findings = check(Source("sample.ts", code.encode(), Language.TYPESCRIPT), Policy())
    assert [(f.rule, f.line, f.message) for f in findings] == [
        ("unused.return", 3, "Return value from 'value' is discarded")
    ]


@pytest.mark.parametrize("other", ["Item", "Other"])
def test_conditional_receivers_require_agreeing_class_identities(other: str) -> None:
    code = (
        "export class Item { constructor(public value: number) {} }\n"
        "export class Other { constructor(public value: number) {} }\n"
        "export function read(flag: boolean): number {\n"
        f"  const item = flag ? new Item(1) : new {other}(2); return item.value;\n"
        "}"
    )
    findings = _unused(code)
    expected_lines = [2] if other == "Item" else [1, 2]
    assert [finding.line for finding in findings] == expected_lines


def test_unrelated_conditions_do_not_narrow_receiver() -> None:
    code = (
        "export class Value { constructor(readonly text: string) {} }\n"
        "export function read(value: Error, flag: boolean): string {\n"
        '  return flag ? value.text : "";\n'
        "}"
    )
    findings = _unused(code)
    assert len(findings) == 1
    assert (findings[0].rule, findings[0].line) == ("unused.parameter", 1)


def test_destructured_constructor_binding_is_not_a_property() -> None:
    code = (
        "export class Item {\n"
        "  value = 1;\n"
        "  constructor({value}: {value: number}) {}\n"
        "  read = (unused: number): number => this.value;\n"
        "}"
    )
    findings = tuple(f for f in _unused(code) if f.rule == "unused.parameter")
    assert [finding.line for finding in findings] == [3, 4]
