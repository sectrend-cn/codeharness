"""Behavioral coverage for directional boundaries and lexical usage evidence."""

from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Finding, Report
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


def _findings(code: str, language: Language, *, external: bool = False) -> tuple[Finding, ...]:
    policy = Policy(third_party_modules=("vendor",) if external else ())
    return check(Source("sample", code.encode(), language), policy)


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def run(used: int, unused: int) -> int:\n    return used\n"),
        (Language.GO, "package sample\nfunc Run(used, unused int) int { return used }"),
        (Language.JAVASCRIPT, "export function run(used, unused) { return used; }"),
        (
            Language.TYPESCRIPT,
            "export function run(used: number, unused: number): number { return used; }",
        ),
        (Language.TSX, "export const Run = (used: string, unused: string) => <div>{used}</div>;"),
    ],
)
def test_reports_only_unread_parameters(language: Language, code: str) -> None:
    findings = [f for f in _findings(code, language) if f.rule == "unused.parameter"]
    assert len(findings) == 1
    assert "'unused'" in findings[0].message
    assert findings[0].severity == "error"


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def _unused() -> int:\n    return 1\n"),
        (Language.GO, "package sample\nfunc unused() int { return 1 }"),
        (Language.JAVASCRIPT, "function unused() { return 1; }"),
        (Language.TYPESCRIPT, "function unused(): number { return 1; }"),
    ],
)
def test_reports_private_functions(language: Language, code: str) -> None:
    assert any(f.rule == "unused.function" for f in _findings(code, language))


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "class Item:\n    value: int\n    def set(self) -> None:\n        self.value = 1\n",
        ),
        (
            Language.GO,
            "package sample\ntype Item struct { value int }\nfunc (i *Item) Set() { i.value = 1 }",
        ),
        (Language.JAVASCRIPT, "class Item { value = 0; set() { this.value = 1; } }"),
        (Language.TYPESCRIPT, "class Item { value: number = 0; set(): void { this.value = 1; } }"),
    ],
)
def test_write_only_fields_are_unused(language: Language, code: str) -> None:
    findings = [f for f in _findings(code, language) if f.rule == "unused.field"]
    assert len(findings) == 1
    assert "'value'" in findings[0].message


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "class Item:\n    value: int\n    def read(self) -> int:\n        return self.value\n",
        ),
        (
            Language.GO,
            (
                "package sample\ntype Item struct { value int }\nfunc (i *Item) "
                "Read() int { return i.value }"
            ),
        ),
        (Language.JAVASCRIPT, "class Item { value = 0; read() { return this.value; } }"),
        (
            Language.TYPESCRIPT,
            "class Item { value: number = 0; read(): number { return this.value; } }",
        ),
    ],
)
def test_read_fields_are_used(language: Language, code: str) -> None:
    assert not any(f.rule == "unused.field" for f in _findings(code, language))


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "from vendor import send\nclass Item:\n    value: int\nitem = Item()\nsend(item)\n",
        ),
        (
            Language.GO,
            (
                'package sample\nimport "vendor"\ntype Item struct { value int '
                "}\nfunc Run() { item := Item{}; vendor.Send(item) }"
            ),
        ),
        (
            Language.JAVASCRIPT,
            (
                'import {send} from "vendor"; class Item { value = 0; } const '
                "item = new Item(); send(item);"
            ),
        ),
        (
            Language.TYPESCRIPT,
            (
                'import {send} from "vendor"; class Item { value: number = 0; } '
                "const item = new Item(); send(item);"
            ),
        ),
    ],
)
def test_library_inputs_exempt_their_fields(language: Language, code: str) -> None:
    assert any(f.rule == "unused.field" for f in _findings(code, language))
    assert not any(f.rule == "unused.field" for f in _findings(code, language, external=True))


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def result() -> int:\n    return 1\nresult()\n"),
        (Language.GO, "package sample\nfunc result() int { return 1 }; func main() { result() }"),
        (Language.JAVASCRIPT, "function result() { return 1; } result();"),
        (Language.TYPESCRIPT, "function result(): number { return 1; } result();"),
    ],
)
def test_discarded_returns_are_warnings(language: Language, code: str) -> None:
    findings = [f for f in _findings(code, language) if f.rule == "unused.return"]
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_warning_only_cli_passes_in_text_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "app.py").write_text("def result() -> int:\n    return 1\nresult()\n")
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert len(report.findings) == 1
    assert report.findings[0].severity == "warning"
    assert main(["--root", str(tmp_path), "--all"]) == 0
    assert "warning: unused.return" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "from vendor import send\noptions: dict[str, object] = {}\nsend(**options)\n",
        ),
        (
            Language.GO,
            (
                'package sample\nimport "vendor"\nfunc Run() { var options '
                "map[string]any; vendor.Send(options) }"
            ),
        ),
        (
            Language.TYPESCRIPT,
            (
                'import {send} from "vendor"; const options: Record<string, '
                "unknown> = {}; send(options);"
            ),
        ),
    ],
)
def test_erased_dictionaries_are_allowed_only_at_library_input(
    language: Language, code: str
) -> None:
    assert any(f.rule in {"type.broad", "type.annotation"} for f in _findings(code, language))
    assert not any(f.rule.startswith("type.") for f in _findings(code, language, external=True))


def test_internal_erased_dictionary_is_not_exempt() -> None:
    code = (
        "from vendor import send\noptions: dict[str, object] = "
        "{}\nsend(**options)\nprint(options)\n"
    )
    assert any(f.rule == "type.annotation" for f in _findings(code, Language.PYTHON, external=True))


def test_fields_are_resolved_per_class() -> None:
    code = (
        "class First:\n    value: int\nclass Second:\n    value: int\n    "
        "def read(self) -> int:\n        return self.value\n"
    )
    findings = [f for f in _findings(code, Language.PYTHON) if f.rule == "unused.field"]
    assert len(findings) == 1
    assert findings[0].line == 2


def test_callback_return_is_library_input() -> None:
    code = (
        "from vendor import register\ndef callback() -> dict[str, "
        "object]:\n    return {}\nregister(callback)\n"
    )
    findings = _findings(code, Language.PYTHON, external=True)
    assert not any(f.rule.startswith("type.") for f in findings)


def test_callback_parameter_requires_typed_conversion() -> None:
    code = (
        "from vendor import register\ndef callback(raw: dict[str, "
        "object]) -> int:\n    return raw['value']\nregister(callback)\n"
    )
    assert any(f.rule == "type.boundary" for f in _findings(code, Language.PYTHON, external=True))


def test_third_party_return_must_not_escape_raw() -> None:
    code = "from vendor import fetch\ndef run() -> int:\n    return fetch()\n"
    assert any(f.rule == "type.boundary" for f in _findings(code, Language.PYTHON, external=True))


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            (
                "from vendor import send\ndef forward(options: dict[str, object]) "
                "-> None:\n    send(**options)\n"
            ),
        ),
        (
            Language.PYTHON,
            (
                "from typing import Any\nfrom vendor import send\ndef "
                "forward(**options: Any) -> None:\n    send(**options)\n"
            ),
        ),
        (
            Language.GO,
            (
                'package sample\nimport "vendor"\nfunc Forward(options '
                "map[string]any) { vendor.Send(options) }"
            ),
        ),
        (
            Language.TYPESCRIPT,
            (
                'import {send} from "vendor"; export function forward(options: '
                "Record<string, unknown>): void { send(options); }"
            ),
        ),
    ],
)
def test_forwarding_parameter_is_library_input(language: Language, code: str) -> None:
    assert not any(f.rule.startswith("type.") for f in _findings(code, language, external=True))


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            (
                "from vendor import register\ndef callback() -> dict[str, "
                "object]:\n    return {}\nregister(callback)\ncallback()\n"
            ),
        ),
        (
            Language.TYPESCRIPT,
            (
                'import {register} from "vendor"; function callback(): '
                "Record<string, unknown> { return {}; } register(callback); callback();"
            ),
        ),
    ],
)
def test_callback_used_in_application_keeps_concrete_contract(
    language: Language, code: str
) -> None:
    assert any(
        f.rule in {"type.annotation", "type.broad"}
        for f in _findings(code, language, external=True)
    )


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.GO,
            (
                'package sample\nimport "vendor"\nfunc callback() map[string]any '
                "{ return nil }; func main() { vendor.Register(callback) }"
            ),
        ),
        (
            Language.TYPESCRIPT,
            (
                'import {register} from "vendor"; const callback = (): '
                "Record<string, unknown> => ({}); register(callback);"
            ),
        ),
        (
            Language.TSX,
            (
                'import {register} from "vendor"; const callback = (): '
                "Record<string, unknown> => ({}); register(callback);"
            ),
        ),
    ],
)
def test_callback_return_boundary_for_other_grammars(language: Language, code: str) -> None:
    assert not any(f.rule.startswith("type.") for f in _findings(code, language, external=True))


def test_callback_dictionary_is_converted_at_ingress() -> None:
    code = (
        "from vendor import register\ndef callback(raw: dict[str, "
        "object]) -> int:\n    return int(raw['value'])\nregister(callback)\n"
    )
    assert not any(
        f.rule.startswith("type.") for f in _findings(code, Language.PYTHON, external=True)
    )


def test_ordinary_dictionary_callback_still_rejects_erasure() -> None:
    code = "def callback(raw: dict[str, object]) -> int:\n    return int(raw['value'])\n"
    assert any(f.rule == "type.annotation" for f in _findings(code, Language.PYTHON, external=True))


def test_third_party_import_shadowing_does_not_grant_exemption() -> None:
    code = (
        "from vendor import send\ndef run(send: int) -> None:\n    "
        "options: dict[str, object] = {}\n    send(options)\n"
    )
    assert any(f.rule == "type.annotation" for f in _findings(code, Language.PYTHON, external=True))


def test_unrelated_erased_types_cannot_hide_inside_dictionary_annotation() -> None:
    code = (
        "from vendor import send\noptions: tuple[dict[str, object], "
        "object] = ({}, 1)\nsend(options)\n"
    )
    assert any(f.rule == "type.annotation" for f in _findings(code, Language.PYTHON, external=True))


def test_shadowed_parameter_is_still_unused() -> None:
    code = "export function run(value: number): void { { const value = 1; console.log(value); } }"
    findings = _findings(code, Language.TYPESCRIPT)
    assert any(f.rule == "unused.parameter" for f in findings)


def test_nested_parameter_does_not_count_as_outer_read() -> None:
    code = (
        "def run(value: int) -> int:\n    def inner(value: int) -> int:\n "
        "       return value\n    return inner(1)\n"
    )
    findings = [f for f in _findings(code, Language.PYTHON) if f.rule == "unused.parameter"]
    assert len(findings) == 1
    assert findings[0].line == 1


def test_closure_read_counts_for_outer_parameter() -> None:
    code = (
        "def run(value: int) -> int:\n    def inner() -> int:\n        "
        "return value\n    return inner()\n"
    )
    assert not any(f.rule == "unused.parameter" for f in _findings(code, Language.PYTHON))


def test_deleted_field_is_not_a_read() -> None:
    code = "class Item:\n    value: int\n    def clear(self) -> None:\n        del self.value\n"
    assert any(f.rule == "unused.field" for f in _findings(code, Language.PYTHON))


def test_fields_of_direct_library_object_are_used() -> None:
    code = "from vendor import send\nclass Item:\n    value: int\nsend(Item())\n"
    assert not any(
        f.rule == "unused.field" for f in _findings(code, Language.PYTHON, external=True)
    )


def test_callback_returned_object_fields_are_used() -> None:
    code = (
        "from vendor import register\nclass Item:\n    value: int\ndef "
        "callback() -> Item:\n    return Item()\nregister(callback)\n"
    )
    assert not any(
        f.rule == "unused.field" for f in _findings(code, Language.PYTHON, external=True)
    )


@pytest.mark.parametrize(
    ("model_path", "model", "consumer_path", "consumer"),
    [
        (
            "models.py",
            "class Item:\n    value: int\n",
            "app.py",
            "from models import Item\ndef read(item: Item) -> int:\n    return item.value\n",
        ),
        (
            "models.ts",
            "export class Item { value: number = 0; }",
            "app.ts",
            (
                'import {Item} from "./models"; export function read(item: Item): '
                "number { return item.value; }"
            ),
        ),
    ],
)
def test_cross_file_field_reads_prevent_false_unused_reports(
    tmp_path: Path, model_path: str, model: str, consumer_path: str, consumer: str
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / model_path).write_text(model)
    (tmp_path / consumer_path).write_text(consumer)
    assert main(["--root", str(tmp_path), "--all"]) == 0


def test_protocol_parameters_have_no_implementation_to_read_them() -> None:
    code = (
        "from typing import Protocol\nclass Reader(Protocol):\n    def "
        "read(self, value: int) -> int: ...\n"
    )
    assert not any(f.rule == "unused.parameter" for f in _findings(code, Language.PYTHON))


@pytest.mark.parametrize(
    "checker",
    ["unused.parameter", "unused.function", "unused.field", "unused.return", "type.boundary"],
)
def test_new_checkers_can_be_disabled_independently(checker: str) -> None:
    code = (
        "from vendor import fetch\nclass Item:\n    value: int\ndef "
        "_unused(parameter: int) -> int:\n    return fetch()\ndef "
        "result() -> int:\n    return 1\nresult()\n"
    )
    source = Source("app.py", code.encode(), Language.PYTHON)
    enabled = check(source, Policy(third_party_modules=("vendor",)))
    policy = Policy.model_validate_json(
        '{"third_party_modules":["vendor"],"checkers":{"' + checker + '":{"enabled":false}}}'
    )
    assert any(f.rule == checker for f in enabled)
    assert check(source, policy) == tuple(f for f in enabled if f.rule != checker)


def test_go_package_usage_spans_files(tmp_path: Path) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "model.go").write_text(
        "package sample\ntype item struct { value int }; func helper() int { return 1 }\n"
    )
    (tmp_path / "consumer.go").write_text(
        "package sample\nfunc Read(i item) int { return i.value + helper() }\n"
    )
    assert main(["--root", str(tmp_path), "--all"]) == 0


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def value() -> int:\n    return 1\n_ = value()\n"),
        (Language.GO, "package sample\nfunc value() int { return 1 }; func main() { _ = value() }"),
        (Language.TYPESCRIPT, "function value(): number { return 1; } void value();"),
    ],
)
def test_explicit_return_discard_still_warns(language: Language, code: str) -> None:
    assert any(
        f.rule == "unused.return" and f.severity == "warning" for f in _findings(code, language)
    )


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "from vendor import fetch\nprint(fetch())\n"),
        (Language.GO, 'package sample\nimport "vendor"\nfunc Read() int { return vendor.Fetch() }'),
        (
            Language.JAVASCRIPT,
            'import {fetch} from "vendor"; export function read() { return fetch(); }',
        ),
        (
            Language.TYPESCRIPT,
            'import {fetch} from "vendor"; export function read(): number { return fetch(); }',
        ),
    ],
)
def test_unconverted_external_results_are_reported(language: Language, code: str) -> None:
    assert any(f.rule == "type.boundary" for f in _findings(code, language, external=True))


def test_external_metaclass_consumes_class_fields() -> None:
    code = "from vendor import Model\nclass Item(Model):\n    value: int\n"
    assert any(f.rule == "unused.field" for f in _findings(code, Language.PYTHON))
    assert not any(
        f.rule == "unused.field" for f in _findings(code, Language.PYTHON, external=True)
    )


def test_protocol_dispatch_does_not_mislabel_implementations() -> None:
    code = (
        "from typing import Protocol\nclass Reader(Protocol):\n"
        "    def read(self) -> int: ...\nclass Implementation:\n"
        "    def read(self) -> int:\n        return 1\n"
        "def run(reader: Reader) -> int:\n    return reader.read()\n"
    )
    assert not any(f.rule == "unused.function" for f in _findings(code, Language.PYTHON))


def test_nested_class_name_does_not_steal_outer_field_reads() -> None:
    code = (
        "class Item:\n    value: int\ndef outer() -> int:\n"
        "    class Item:\n        value: int\n"
        "    item = Item()\n    return item.value\n"
    )
    fields = [f for f in _findings(code, Language.PYTHON) if f.rule == "unused.field"]
    assert len(fields) == 1
    assert fields[0].line == 2


@pytest.mark.parametrize(
    "binding", ['const sdk = require("vendor");', 'const {send: emit} = require("vendor");']
)
def test_commonjs_library_inputs_consume_object_fields(binding: str) -> None:
    callee = "sdk.send" if "sdk" in binding else "emit"
    code = binding + f" class Item {{ value = 0; }} {callee}(new Item());"
    assert not any(
        f.rule == "unused.field" for f in _findings(code, Language.JAVASCRIPT, external=True)
    )


def test_later_function_definition_shadows_external_import() -> None:
    code = (
        "from vendor import send\ndef send(value: int) -> int:\n    return value\n"
        "options: dict[str, object] = {}\nsend(options)\n"
    )
    assert any(f.rule == "type.annotation" for f in _findings(code, Language.PYTHON, external=True))


def test_cross_file_reads_do_not_hide_unread_fields_on_another_class(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/models.py").write_text(
        "class Used:\n    value: int\nclass Unused:\n    value: int\n"
    )
    (tmp_path / "pkg/consumer.py").write_text(
        "from .models import Used\ndef read(item: Used) -> int:\n    return item.value\n"
    )
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.rule) for f in report.findings] == [
        ("pkg/models.py", 4, "unused.field")
    ]


@pytest.mark.parametrize("contract", ["Payload", "Payload | None"])
def test_specialized_library_objects_preserve_concrete_contracts(contract: str) -> None:
    code = (
        "from vendor import Adapter\nclass Payload:\n    value: int\n"
        f"adapter = Adapter[{contract}](Payload)\nadapter.parse('input')\n"
    )
    assert not any(
        f.rule == "type.boundary" for f in _findings(code, Language.PYTHON, external=True)
    )


def test_erased_specialization_is_not_a_typed_library_result() -> None:
    code = "from vendor import Adapter\nadapter = Adapter[object](object)\nadapter.parse('input')\n"
    assert any(f.rule == "type.boundary" for f in _findings(code, Language.PYTHON, external=True))


def test_external_schema_metadata_is_not_an_erased_application_result() -> None:
    code = (
        "from typing import Annotated\nfrom vendor import Model, Field\n"
        "type Count = Annotated[int, Field(default=1)]\nclass Item(Model):\n"
        "    value: int = Field(default=1)\n    def read(self) -> int:\n        return self.value\n"
    )
    assert not any(
        f.rule == "type.boundary" for f in _findings(code, Language.PYTHON, external=True)
    )


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() {}\n"
            "func main() { items := []item{{}}; items[0].render() }\n",
            id="slice-literal",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() {}\n"
            "func main() { items := make([]item, 1); items[0].render() }\n",
            id="make-builtin",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() {}\n"
            'func main() { m := map[string]item{}; m["k"].render() }\n',
            id="map-literal",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i *item) render() {}\n"
            "func main() { p := new(item); p.render() }\n",
            id="new-builtin",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i *item) render() {}\n"
            "func main() { p := &item{}; p.render() }\n",
            id="address-of-composite",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() {}\n"
            "func main() { items := [][]item{{}}; items[0][0].render() }\n",
            id="nested-slice",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() {}\n"
            "func get() []item { return nil }\n"
            "func main() { get()[0].render() }\n",
            id="chained-call",
        ),
    ],
)
def test_value_inferred_containers_resolve_member_calls(code: str) -> None:
    findings = [f for f in _findings(code, Language.GO) if f.rule == "unused.function"]
    assert findings == []


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            "package main\ntype key struct{}\ntype item struct{}\n"
            "func (k key) render() {}\nfunc (i item) render() {}\n"
            "func main() { m := map[key]item{}; m[key{}].render() }\n",
            id="value-path",
        ),
        pytest.param(
            "package main\ntype key struct{}\ntype item struct{}\n"
            "func (k key) render() {}\nfunc (i item) render() {}\n"
            "func main() { var m map[key]item; m[key{}].render() }\n",
            id="annotation-path",
        ),
    ],
)
def test_value_inferred_map_literals_use_element_not_key_type(code: str) -> None:
    findings = [f for f in _findings(code, Language.GO) if f.rule == "unused.function"]
    assert len(findings) == 1
    assert findings[0].line == 4
    assert findings[0].severity == "error"
    assert "'render'" in findings[0].message


def test_unresolved_go_method_reads_defer_like_other_languages() -> None:
    chained = (
        "package main\ntype item struct{}\nfunc (i item) render() {}\n"
        "func get() []item { return nil }\nfunc main() { get()[0].render() }\n"
    )
    never_called = "package main\ntype item struct{}\nfunc (i item) render() {}\n"
    deferred = [f for f in _findings(chained, Language.GO) if f.rule == "unused.function"]
    reported = [f for f in _findings(never_called, Language.GO) if f.rule == "unused.function"]
    assert deferred == []
    assert [(f.line, f.severity) for f in reported] == [(3, "error")]


def test_discarded_results_on_value_inferred_receivers_warn() -> None:
    code = (
        "package main\ntype item struct{}\nfunc (i item) render() int { return 1 }\n"
        "func main() { items := []item{{}}; items[0].render() }\n"
    )
    findings = _findings(code, Language.GO)
    assert [(f.rule, f.line, f.severity) for f in findings] == [("unused.return", 4, "warning")]
    assert "'render'" in findings[0].message


def _shadowed_new_source(main_body: str) -> str:
    return (
        "package main\ntype item struct{}\ntype other struct{}\n"
        "func (i item) render() int { return 1 }\n"
        "func (o other) render() {}\n"
        "func new(value item) other { _ = value; return other{} }\n"
        f"func main() {{ {main_body} }}\n"
    )


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            _shadowed_new_source("var v item; p := new(v); p.render()"), id="variable-argument"
        ),
        pytest.param(_shadowed_new_source("p := new(item); p.render()"), id="type-argument"),
        pytest.param(
            _shadowed_new_source("p := (new(item)); p.render()"), id="parenthesized-type-argument"
        ),
    ],
)
def test_shadowed_new_calls_use_the_declared_return_type(code: str) -> None:
    findings = _findings(code, Language.GO)
    assert [(f.rule, f.line, f.severity) for f in findings] == [("unused.function", 4, "error")]
    assert "'render'" in findings[0].message


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            "package main\ntype item struct{}\ntype other struct{}\n"
            "func (i item) render() int { return 1 }\n"
            "func (o other) render() {}\n"
            "func main() {\n"
            "\tnew := func(v item) other { _ = v; return other{} }\n"
            "\tp := new(item)\n\tp.render()\n}\n",
            id="local-function-literal",
        ),
        pytest.param(
            "package main\ntype item struct{}\ntype other struct{}\n"
            "func (i item) render() int { return 1 }\n"
            "func (o *other) render() {}\n"
            "func new(value item) *other { _ = value; return nil }\n"
            "func main() { p := *new(item); p.render() }\n",
            id="dereferenced-call",
        ),
    ],
)
def test_shadowed_new_calls_without_a_resolved_target_defer(code: str) -> None:
    assert _findings(code, Language.GO) == ()


def _type_conversion_source(spelling: str, argument: str) -> str:
    return (
        "package main\ntype item struct{}\n"
        "func (i item) render() {}\n"
        f"type {spelling} item\n"
        f"func (n {spelling}) render() int {{ return 1 }}\n"
        f"func main() {{ var v item; p := {spelling}({argument}); p.render() }}\n"
    )


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(_type_conversion_source("new", "v"), id="variable-argument"),
        pytest.param(_type_conversion_source("new", "item"), id="type-argument"),
    ],
)
def test_type_conversion_named_new_resolves_the_declared_type(code: str) -> None:
    findings = _findings(code, Language.GO)
    assert [(f.rule, f.line, f.severity) for f in findings] == [
        ("unused.function", 3, "error"),
        ("unused.return", 6, "warning"),
    ]
    assert "'render'" in findings[0].message
    assert "'render'" in findings[1].message


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(_type_conversion_source("make", "v"), id="variable-argument"),
        pytest.param(_type_conversion_source("make", "item"), id="type-argument"),
    ],
)
def test_type_conversion_named_make_resolves_the_declared_type(code: str) -> None:
    findings = _findings(code, Language.GO)
    assert [(f.rule, f.line, f.severity) for f in findings] == [
        ("unused.function", 3, "error"),
        ("unused.return", 6, "warning"),
    ]
    assert "'render'" in findings[0].message
    assert "'render'" in findings[1].message


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            "package main\ntype item struct{}\ntype other struct{}\n"
            "func (i item) render() int { return 1 }\n"
            "func (o other) render() {}\n"
            "func main() { p := model.New(); p.render() }\n",
            id="no-argument",
        ),
        pytest.param(
            "package main\ntype item struct{}\ntype other struct{}\n"
            "func (i item) render() int { return 1 }\n"
            "func (o other) render() {}\n"
            "func main() { p := model.New(item); p.render() }\n",
            id="type-argument",
        ),
    ],
)
def test_package_qualified_calls_keep_the_existing_path(code: str) -> None:
    assert _findings(code, Language.GO) == ()


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() int { return 1 }\n"
            "func main() { items := []item{{}}; items[0].render() }\n",
            id="slice-literal",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() int { return 1 }\n"
            "func main() { items := make([]item, 1); items[0].render() }\n",
            id="make-builtin",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() int { return 1 }\n"
            'func main() { m := map[string]item{}; m["k"].render() }\n',
            id="map-literal",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i *item) render() int { return 1 }\n"
            "func main() { p := new(item); p.render() }\n",
            id="new-builtin",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i *item) render() int { return 1 }\n"
            "func main() { p := &item{}; p.render() }\n",
            id="address-of-composite",
        ),
        pytest.param(
            "package main\ntype item struct{}\nfunc (i item) render() int { return 1 }\n"
            "func main() { items := [][]item{{}}; items[0][0].render() }\n",
            id="nested-slice",
        ),
    ],
)
def test_value_inferred_receivers_report_discarded_results(code: str) -> None:
    findings = _findings(code, Language.GO)
    assert [(f.rule, f.line, f.severity) for f in findings] == [("unused.return", 4, "warning")]
    assert "'render'" in findings[0].message


def test_unresolved_chained_receivers_stay_deferred() -> None:
    code = (
        "package main\ntype item struct{}\nfunc (i item) render() int { return 1 }\n"
        "func get() []item { return nil }\nfunc main() { get()[0].render() }\n"
    )
    assert _findings(code, Language.GO) == ()


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(
            "package main\ntype key struct{}\ntype item struct{}\n"
            "func (k key) render() {}\nfunc (i item) render() int { return 1 }\n"
            "func main() { items := []*map[key]item{}; (*items[0])[key{}].render() }\n",
            id="value-path",
        ),
        pytest.param(
            "package main\ntype key struct{}\ntype item struct{}\n"
            "func (k key) render() {}\nfunc (i item) render() int { return 1 }\n"
            "func Run(items []*map[key]item) { (*items[0])[key{}].render() }\n",
            id="annotation-path",
        ),
    ],
)
def test_pointer_to_map_elements_resolve_the_value_type(code: str) -> None:
    findings = _findings(code, Language.GO)
    assert [(f.rule, f.line, f.severity) for f in findings] == [
        ("unused.function", 4, "error"),
        ("unused.return", 6, "warning"),
    ]


_PYTHON_RENDER_ITEM = "class Item:\n    def render(self) -> int:\n        return 1\n"
_JAVASCRIPT_RENDER_ITEM = "class Item { render() { return 1; } }\n"
_TYPESCRIPT_RENDER_ITEM = "class Item { render(): number { return 1; } }\n"


def _discarded_render(line: int) -> tuple[Finding, ...]:
    return (
        Finding(
            path="sample",
            line=line,
            column=1,
            rule="unused.return",
            message="Return value from 'render' is discarded",
            severity="warning",
        ),
    )


@pytest.mark.parametrize(
    ("language", "declaration", "binding", "call", "line"),
    [
        (Language.PYTHON, _PYTHON_RENDER_ITEM, "items = [Item()]\n", "items[0].render()\n", 5),
        (
            Language.JAVASCRIPT,
            _JAVASCRIPT_RENDER_ITEM,
            "const items = [new Item()];\n",
            "items[0].render();\n",
            3,
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM,
            "const items = [new Item()];\n",
            "items[0].render();\n",
            3,
        ),
        (
            Language.JAVASCRIPT,
            _JAVASCRIPT_RENDER_ITEM,
            "const items = [Item()];\n",
            "items[0].render();\n",
            3,
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM,
            "const items = [Item()];\n",
            "items[0].render();\n",
            3,
        ),
    ],
)
def test_literal_element_calls_resolve_and_warn(
    language: Language, declaration: str, binding: str, call: str, line: int
) -> None:
    assert _findings(declaration + binding + call, language) == _discarded_render(line)


@pytest.mark.parametrize(
    ("language", "code", "line"),
    [
        (
            Language.PYTHON,
            _PYTHON_RENDER_ITEM + "items: list[Item] = []\nitems[0].render()\n",
            5,
        ),
        (Language.PYTHON, _PYTHON_RENDER_ITEM + "item = Item()\nitem.render()\n", 5),
        (
            Language.JAVASCRIPT,
            _JAVASCRIPT_RENDER_ITEM + "const item = new Item();\nitem.render();\n",
            3,
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM + "const items: Item[] = [];\nitems[0].render();\n",
            3,
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM + "const item = new Item();\nitem.render();\n",
            3,
        ),
    ],
)
def test_existing_receiver_findings_stay_frozen(language: Language, code: str, line: int) -> None:
    assert _findings(code, language) == _discarded_render(line)


@pytest.mark.parametrize(
    ("language", "declaration", "expression", "ending"),
    [
        (Language.PYTHON, _PYTHON_RENDER_ITEM, "[Item()]", "\nprint(items[0].render())\n"),
        (
            Language.JAVASCRIPT,
            _JAVASCRIPT_RENDER_ITEM + "const ",
            "[new Item()]",
            ";\nconsole.log(items[0].render());\n",
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM + "const ",
            "[new Item()]",
            ";\nconsole.log(items[0].render());\n",
        ),
    ],
)
@pytest.mark.parametrize("literal", [False, True], ids=["ordinary-literal", "constructor-element"])
def test_consumed_literal_element_results_keep_empty_findings(
    language: Language, declaration: str, expression: str, ending: str, literal: bool
) -> None:
    value = expression if literal else "[1]"
    assert _findings(declaration + "items = " + value + ending, language) == ()


@pytest.mark.parametrize(
    ("language", "code", "line", "column"),
    [
        (Language.PYTHON, _PYTHON_RENDER_ITEM, 2, 9),
        (Language.JAVASCRIPT, _JAVASCRIPT_RENDER_ITEM + "new Item();\n", 1, 14),
        (Language.TYPESCRIPT, _TYPESCRIPT_RENDER_ITEM + "new Item();\n", 1, 14),
    ],
)
def test_literal_inference_keeps_genuinely_unused_methods(
    language: Language, code: str, line: int, column: int
) -> None:
    assert _findings(code, language) == (
        Finding(
            path="sample",
            line=line,
            column=column,
            rule="unused.function",
            message="Function 'render' has no resolved read usage in the audited snapshots",
        ),
    )


@pytest.mark.parametrize(
    "value",
    [
        "[]",
        "[1]",
        "[1, Item()]",
        "[Item]",
        "[pkg.Item()]",
        "(Item(),)",
        "{Item()}",
        "[Item() for entry in []]",
        "[make()]",
    ],
)
def test_python_literal_inference_defers_unsupported_elements(value: str) -> None:
    code = _PYTHON_RENDER_ITEM + f"items = {value}\nitems[0].render()\n"
    assert _findings(code, Language.PYTHON) == ()


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT])
@pytest.mark.parametrize(
    "value",
    [
        "[]",
        "[1]",
        "[1, new Item()]",
        "[Item]",
        "[new pkg.Item()]",
        "[pkg.Item()]",
        "[, new Item()]",
        "[...others]",
        "{value: new Item()}",
        "[make()]",
    ],
)
def test_javascript_literal_inference_defers_unsupported_elements(
    language: Language, value: str
) -> None:
    code = _JAVASCRIPT_RENDER_ITEM + f"const items = {value};\nitems[0].render();\n"
    assert _findings(code, language) == ()


@pytest.mark.parametrize(
    ("language", "code", "line"),
    [
        (
            Language.PYTHON,
            _PYTHON_RENDER_ITEM + "items = [\n# element\nItem(), 1]\nitems[0].render()\n",
            7,
        ),
        (
            Language.JAVASCRIPT,
            _JAVASCRIPT_RENDER_ITEM
            + "const items = [/* element */ new Item(), 1];\nitems[0].render();\n",
            3,
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM
            + "const items = [/* element */ new Item(), 1];\nitems[0].render();\n",
            3,
        ),
        (Language.PYTHON, _PYTHON_RENDER_ITEM + "for item in [Item()]:\n    item.render()\n", 5),
    ],
)
def test_literal_first_element_and_iteration_receivers_warn(
    language: Language, code: str, line: int
) -> None:
    findings = _findings(code, language)
    assert [(f.rule, f.line, f.severity) for f in findings] == [("unused.return", line, "warning")]
    assert "'render'" in findings[0].message


@pytest.mark.parametrize(
    ("language", "code", "unused_line", "unused_column", "call_line"),
    [
        (
            Language.PYTHON,
            _PYTHON_RENDER_ITEM + "class Other:\n    def render(self) -> int:\n        return 2\n"
            "items = [Item()]\nitems[0].render()\n",
            5,
            9,
            8,
        ),
        (
            Language.JAVASCRIPT,
            _JAVASCRIPT_RENDER_ITEM + "class Other { render() { return 2; } }\nnew Other();\n"
            "const items = [new Item()];\nitems[0].render();\n",
            2,
            15,
            5,
        ),
        (
            Language.TYPESCRIPT,
            _TYPESCRIPT_RENDER_ITEM
            + "class Other { render(): number { return 2; } }\nnew Other();\n"
            "const items = [new Item()];\nitems[0].render();\n",
            2,
            15,
            5,
        ),
    ],
)
def test_literal_element_reads_belong_only_to_the_constructed_class(
    language: Language, code: str, unused_line: int, unused_column: int, call_line: int
) -> None:
    assert _findings(code, language) == (
        Finding(
            path="sample",
            line=unused_line,
            column=unused_column,
            rule="unused.function",
            message="Function 'render' has no resolved read usage in the audited snapshots",
        ),
        *_discarded_render(call_line),
    )


_GO_ELEMENT_OVERWRITE = """package main

type Item struct{}

type Other struct{}

func (i Item) render() int { return 1 }

func (o Other) render() int { return 2 }

func main() {
	b := []Item{{}}
	b[0] = Other{}
	b[1].render()
}
"""

_GO_ELEMENT_CONTROL = """package main

type Item struct{}

type Other struct{}

type Spare struct{}

func (i Item) render() int { return 1 }

func (o Other) render() int { return 2 }

func (s Spare) never() int { return 3 }

func main() {
	b := []Item{{}}
	b[0] = Other{}
}
"""

_GO_ELEMENT_DIFFERENT_NAME = """package main

type Item struct{}

type Other struct{}

func (i Item) render() int { return 1 }

func (o Other) write() int { return 2 }

func main() {
	b := []Item{{}}
	b[0] = Other{}
	b[1].render()
}
"""

_GO_ELEMENT_PARAMETER = """package main

type Item struct{}

func (i Item) render() int { return 1 }

func Run(b []int) {
	b[0] = Item{}
	b[1].render()
}
"""

_PYTHON_ELEMENT_OVERWRITE = """class Item:
    def render(self) -> int:
        return 1


class Other(Item):
    def render(self) -> int:
        return 2


def run() -> None:
    b = [Item()]
    b[0] = Other()
    b[1].render()
"""

_PYTHON_ELEMENT_CONTROL = """class Item:
    def render(self) -> int:
        return 1


class Other(Item):
    def render(self) -> int:
        return 2


class Spare:
    def never(self) -> int:
        return 3


def run() -> None:
    b = [Item()]
    b[0] = Other()
"""

_PYTHON_ELEMENT_DIFFERENT_NAME = """class Item:
    def render(self) -> int:
        return 1


class Other:
    def write(self) -> int:
        return 2


def run() -> None:
    b = [Item()]
    b[0] = Other()
    b[1].render()
"""

_PYTHON_ELEMENT_PARAMETER = """class Item:
    def render(self) -> int:
        return 1


def run(b: list[int]) -> None:
    b[0] = Item()
    b[1].render()
"""

_JAVASCRIPT_ELEMENT_OVERWRITE = """class Item { render() { return 1; } }
class Other { render() { return 2; } }
const b = [new Item()];
b[0] = new Other();
b[1].render();
"""

_JAVASCRIPT_ELEMENT_CONTROL = """class Item { render() { return 1; } }
class Other { render() { return 2; } }
class Spare { never() { return 3; } }
const b = [new Item()];
b[0] = new Other();
"""

_JAVASCRIPT_ELEMENT_DIFFERENT_NAME = """class Item { render() { return 1; } }
class Other { write() { return 2; } }
const b = [new Item()];
b[0] = new Other();
b[1].render();
"""

_JAVASCRIPT_ELEMENT_PARAMETER = """class Item { render() { return 1; } }
export function run(b) {
  b[0] = new Item();
  b[1].render();
}
"""

_TYPESCRIPT_ELEMENT_OVERWRITE = """class Item { render(): number { return 1; } }
class Other { render(): number { return 2; } }
const b = [new Item()];
b[0] = new Other();
b[1].render();
"""

_TYPESCRIPT_ELEMENT_CONTROL = """class Item { render(): number { return 1; } }
class Other { render(): number { return 2; } }
class Spare { never(): number { return 3; } }
const b = [new Item()];
b[0] = new Other();
"""

_TYPESCRIPT_ELEMENT_DIFFERENT_NAME = """class Item { render(): number { return 1; } }
class Other { write(): number { return 2; } }
const b = [new Item()];
b[0] = new Other();
b[1].render();
"""

_TYPESCRIPT_ELEMENT_PARAMETER = """class Item { render(): number { return 1; } }
export function run(b: Record<string, number>) {
  b[0] = new Item();
  b[1].render();
}
"""

_JAVA_ELEMENT_PARAMETER = """class E {
    static class Item {
        private int m() { return 1; }
    }

    void run(int[] b) {
        b[0] = new Item();
        b[1].m();
    }
}
"""


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        pytest.param(
            Language.GO,
            _GO_ELEMENT_OVERWRITE,
            (("unused.function", 9, "error"), ("unused.return", 14, "warning")),
            id="go",
        ),
        pytest.param(
            Language.PYTHON,
            _PYTHON_ELEMENT_OVERWRITE,
            (("unused.return", 14, "warning"),),
            id="python",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_ELEMENT_OVERWRITE,
            (("unused.function", 2, "error"), ("unused.return", 5, "warning")),
            id="javascript",
        ),
        pytest.param(
            Language.TYPESCRIPT,
            _TYPESCRIPT_ELEMENT_OVERWRITE,
            (("unused.function", 2, "error"), ("unused.return", 5, "warning")),
            id="typescript",
        ),
    ],
)
def test_element_writes_keep_the_container_element_type(
    language: Language, code: str, expected: tuple[tuple[str, int, str], ...]
) -> None:
    findings = _findings(code, language)
    assert tuple((f.rule, f.line, f.severity) for f in findings) == expected
    assert all("'render'" in f.message for f in findings)


@pytest.mark.parametrize(
    ("language", "code", "lines"),
    [
        pytest.param(Language.GO, _GO_ELEMENT_CONTROL, (9, 11, 13), id="go"),
        pytest.param(Language.PYTHON, _PYTHON_ELEMENT_CONTROL, (2, 7, 12), id="python"),
        pytest.param(Language.JAVASCRIPT, _JAVASCRIPT_ELEMENT_CONTROL, (1, 2, 3), id="javascript"),
        pytest.param(Language.TYPESCRIPT, _TYPESCRIPT_ELEMENT_CONTROL, (1, 2, 3), id="typescript"),
    ],
)
def test_element_write_controls_keep_unused_methods_reported(
    language: Language, code: str, lines: tuple[int, ...]
) -> None:
    findings = _findings(code, language)
    assert tuple((f.rule, f.line, f.severity) for f in findings) == tuple(
        ("unused.function", line, "error") for line in lines
    )
    assert all("has no resolved read usage" in f.message for f in findings)


@pytest.mark.parametrize(
    ("language", "code", "write_line", "call_line"),
    [
        pytest.param(Language.GO, _GO_ELEMENT_DIFFERENT_NAME, 9, 14, id="go"),
        pytest.param(Language.PYTHON, _PYTHON_ELEMENT_DIFFERENT_NAME, 7, 14, id="python"),
        pytest.param(
            Language.JAVASCRIPT, _JAVASCRIPT_ELEMENT_DIFFERENT_NAME, 2, 5, id="javascript"
        ),
        pytest.param(
            Language.TYPESCRIPT, _TYPESCRIPT_ELEMENT_DIFFERENT_NAME, 2, 5, id="typescript"
        ),
    ],
)
def test_different_element_write_types_keep_the_container_owner(
    language: Language, code: str, write_line: int, call_line: int
) -> None:
    findings = _findings(code, language)
    assert tuple((f.rule, f.line, f.severity) for f in findings) == (
        ("unused.function", write_line, "error"),
        ("unused.return", call_line, "warning"),
    )
    assert "'write'" in findings[0].message
    assert "'render'" in findings[1].message


@pytest.mark.parametrize(
    ("language", "code"),
    [
        pytest.param(Language.PYTHON, _PYTHON_ELEMENT_PARAMETER, id="python-list-int"),
        pytest.param(Language.GO, _GO_ELEMENT_PARAMETER, id="go-int-slice"),
        pytest.param(Language.JAVASCRIPT, _JAVASCRIPT_ELEMENT_PARAMETER, id="javascript-plain"),
        pytest.param(Language.TYPESCRIPT, _TYPESCRIPT_ELEMENT_PARAMETER, id="typescript-record"),
        pytest.param(Language.JAVA, _JAVA_ELEMENT_PARAMETER, id="java-int-array"),
    ],
)
def test_element_writes_to_parameters_keep_the_fallback_protection(
    language: Language, code: str
) -> None:
    assert _findings(code, language) == ()


_PYTHON_ELEMENT_INGRESS = """from vendor import fetch


def run() -> None:
    items = [0]
    items[0] = fetch()
"""

_GO_ELEMENT_INGRESS = """package main

import "vendor"

func Run() {
	items := []int{0}
	items[0] = vendor.Fetch()
}
"""

_JAVASCRIPT_ELEMENT_INGRESS = """import {fetch} from "vendor";
const items = [0];
items[0] = fetch();
"""

_TYPESCRIPT_ELEMENT_INGRESS = """import {fetch} from "vendor";
const items: number[] = [0];
items[0] = fetch();
"""

_PYTHON_REBINDING_INGRESS = """from vendor import fetch


def run() -> None:
    result = fetch()
    print(result)
"""

_GO_REBINDING_INGRESS = """package main

import "vendor"

func Run() {
	result := vendor.Fetch()
	_ = result
}
"""

_JAVASCRIPT_REBINDING_INGRESS = """import {fetch} from "vendor";
const result = fetch();
console.log(result);
"""

_TYPESCRIPT_REBINDING_INGRESS = """import {fetch} from "vendor";
const result = fetch();
console.log(result);
"""


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        pytest.param(
            Language.PYTHON,
            _PYTHON_ELEMENT_INGRESS,
            (("type.boundary", 5, 5, "error"),),
            id="python",
        ),
        pytest.param(
            Language.GO, _GO_ELEMENT_INGRESS, (("type.boundary", 6, 2, "error"),), id="go"
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_ELEMENT_INGRESS,
            (("type.boundary", 2, 7, "error"),),
            id="javascript",
        ),
        pytest.param(
            Language.TYPESCRIPT,
            _TYPESCRIPT_ELEMENT_INGRESS,
            (("type.boundary", 2, 7, "error"),),
            id="typescript",
        ),
    ],
)
def test_element_write_restores_third_party_ingress_report(
    language: Language, code: str, expected: tuple[tuple[str, int, int, str], ...]
) -> None:
    findings = _findings(code, language, external=True)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in findings) == expected
    assert [f.message for f in findings] == [
        "Convert the third-party result into a typed object at ingress"
    ]
    assert all("items" in code.splitlines()[f.line - 1] for f in findings)


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        pytest.param(
            Language.PYTHON,
            _PYTHON_REBINDING_INGRESS,
            (("type.boundary", 5, 5, "error"),),
            id="python",
        ),
        pytest.param(
            Language.GO, _GO_REBINDING_INGRESS, (("type.boundary", 6, 2, "error"),), id="go"
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_REBINDING_INGRESS,
            (("type.boundary", 2, 7, "error"),),
            id="javascript",
        ),
        pytest.param(
            Language.TYPESCRIPT,
            _TYPESCRIPT_REBINDING_INGRESS,
            (("type.boundary", 2, 7, "error"),),
            id="typescript",
        ),
    ],
)
def test_plain_rebinding_keeps_third_party_ingress_report(
    language: Language, code: str, expected: tuple[tuple[str, int, int, str], ...]
) -> None:
    findings = _findings(code, language, external=True)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in findings) == expected
    assert [f.message for f in findings] == [
        "Convert the third-party result into a typed object at ingress"
    ]
    assert all("result" in code.splitlines()[f.line - 1] for f in findings)


_PYTHON_ELEMENT_INGRESS_MIXED = """from vendor import fetch


def run() -> None:
    items = [0]
    items[0] = 1
    items[0] = fetch()
"""

_PYTHON_ELEMENT_INGRESS_TWICE = """from vendor import fetch, load


def run() -> None:
    items = [0]
    items[0] = fetch()
    items[1] = load()
"""

_PYTHON_ELEMENT_INGRESS_TYPED = """from vendor import fetch


class Item:
    def __init__(self, raw: str) -> None:
        self.raw = raw

    def value(self) -> int:
        return len(self.raw)


def run() -> None:
    items = [Item("a")]
    items[0] = Item(fetch())
    print(items[1].value())
"""

_PYTHON_ELEMENT_INGRESS_CONVERTER = """from vendor import fetch


def convert(raw: str) -> int:
    return len(raw)


def run() -> None:
    items = [0]
    items[0] = convert(fetch())
    print(items[1])
"""

_PYTHON_ELEMENT_INGRESS_EXTERNAL_FIELD = """from vendor import fetch, send


class Item:
    slots: list[int]

    def load(self) -> None:
        self.slots[0] = fetch()

    def read(self) -> int:
        return self.slots[0]


def run() -> None:
    item = Item()
    item.load()
    print(item.read())
    send(item)
"""

_PYTHON_ELEMENT_INGRESS_INEFFECTIVE_FIELD = """from vendor import fetch


class Item:
    slots: list[int]

    def load(self) -> None:
        self.slots[0] = fetch()

    def read(self) -> int:
        return self.slots[0]


def run() -> None:
    item = Item()
    item.load()
    print(item.read())
"""


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        pytest.param(
            _PYTHON_ELEMENT_INGRESS_MIXED, (("type.boundary", 5, 5, "error"),), id="mixed-write"
        ),
        pytest.param(
            _PYTHON_ELEMENT_INGRESS_TWICE,
            (("type.boundary", 5, 5, "error"),),
            id="two-third-party-writes-report-once",
        ),
        pytest.param(_PYTHON_ELEMENT_INGRESS_TYPED, (), id="typed-construction-converts"),
        pytest.param(_PYTHON_ELEMENT_INGRESS_CONVERTER, (), id="project-converter-converts"),
        pytest.param(
            _PYTHON_ELEMENT_INGRESS_EXTERNAL_FIELD, (), id="externally-used-field-is-suppressed"
        ),
        pytest.param(
            _PYTHON_ELEMENT_INGRESS_INEFFECTIVE_FIELD,
            (("type.boundary", 5, 5, "error"),),
            id="field-without-external-use-reports",
        ),
    ],
)
def test_element_write_ingress_follows_assigned_value_evidence(
    code: str, expected: tuple[tuple[str, int, int, str], ...]
) -> None:
    findings = _findings(code, Language.PYTHON, external=True)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in findings) == expected
    assert all(
        f.message == "Convert the third-party result into a typed object at ingress"
        for f in findings
    )


_PYTHON_ELEMENT_INGRESS_FORWARDED = """from vendor import fetch


def run() -> None:
    raw = fetch()
    items = [0]
    items[0] = raw
    print(items[1])
"""


def test_element_write_of_forwarded_value_reports_at_the_intermediate_binding() -> None:
    findings = _findings(_PYTHON_ELEMENT_INGRESS_FORWARDED, Language.PYTHON, external=True)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in findings) == (
        ("type.boundary", 5, 5, "error"),
    )
    assert "raw = fetch()" in _PYTHON_ELEMENT_INGRESS_FORWARDED.splitlines()[4]
    assert all(f.line != 6 for f in findings)


_JAVASCRIPT_ELEMENT_WRITE_PLAIN = """class Item { m() { return 1; } }
class Other { m() { return 2; } }
const b = [new Item()];
b[0] = new Other();
b[1].m();
"""

_JAVASCRIPT_ELEMENT_WRITE_PARENTHESIZED = """class Item { m() { return 1; } }
class Other { m() { return 2; } }
const b = [new Item()];
(b[0]) = new Other();
b[1].m();
"""

_TYPESCRIPT_ELEMENT_WRITE_PLAIN = """class Item { m(): number { return 1; } }
class Other { m(): number { return 2; } }
const b = [new Item()];
b[0] = new Other();
b[1].m();
"""

_TYPESCRIPT_ELEMENT_WRITE_PARENTHESIZED = """class Item { m(): number { return 1; } }
class Other { m(): number { return 2; } }
const b = [new Item()];
(b[0]) = new Other();
b[1].m();
"""

_GO_ELEMENT_WRITE_PLAIN = """package main

type Item struct{}

type Other struct{}

func (i Item) render() int { return 1 }

func (o Other) render() int { return 2 }

func main() {
	b := []Item{{}}
	b[0] = Other{}
	b[1].render()
}
"""

_GO_ELEMENT_WRITE_PARENTHESIZED = """package main

type Item struct{}

type Other struct{}

func (i Item) render() int { return 1 }

func (o Other) render() int { return 2 }

func main() {
	b := []Item{{}}
	(b[0]) = Other{}
	b[1].render()
}
"""

_PYTHON_ELEMENT_WRITE_PLAIN = """class Item:
    def m(self) -> int:
        return 1


class Other(Item):
    def m(self) -> int:
        return 2


def run() -> None:
    b = [Item()]
    b[0] = Other()
    b[1].m()
"""

_PYTHON_ELEMENT_WRITE_PARENTHESIZED = """class Item:
    def m(self) -> int:
        return 1


class Other(Item):
    def m(self) -> int:
        return 2


def run() -> None:
    b = [Item()]
    (b[0]) = Other()
    b[1].m()
"""


@pytest.mark.parametrize(
    ("language", "plain", "parenthesized", "expected"),
    [
        pytest.param(
            Language.GO,
            _GO_ELEMENT_WRITE_PLAIN,
            _GO_ELEMENT_WRITE_PARENTHESIZED,
            (("unused.function", 9, 16, "error"), ("unused.return", 14, 2, "warning")),
            id="go",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_ELEMENT_WRITE_PLAIN,
            _JAVASCRIPT_ELEMENT_WRITE_PARENTHESIZED,
            (("unused.function", 2, 15, "error"), ("unused.return", 5, 1, "warning")),
            id="javascript",
        ),
        pytest.param(
            Language.TYPESCRIPT,
            _TYPESCRIPT_ELEMENT_WRITE_PLAIN,
            _TYPESCRIPT_ELEMENT_WRITE_PARENTHESIZED,
            (("unused.function", 2, 15, "error"), ("unused.return", 5, 1, "warning")),
            id="typescript",
        ),
        pytest.param(
            Language.PYTHON,
            _PYTHON_ELEMENT_WRITE_PLAIN,
            _PYTHON_ELEMENT_WRITE_PARENTHESIZED,
            (("unused.return", 14, 5, "warning"),),
            id="python-tuple-pattern",
        ),
    ],
)
def test_parenthesized_element_writes_match_unparenthesized(
    language: Language,
    plain: str,
    parenthesized: str,
    expected: tuple[tuple[str, int, int, str], ...],
) -> None:
    parenthesized_findings = _findings(parenthesized, language)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in parenthesized_findings) == expected
    assert parenthesized_findings == _findings(plain, language)
    for finding in parenthesized_findings:
        if finding.rule == "unused.function":
            assert "Other" in parenthesized.splitlines()[finding.line - 1]
        if finding.rule == "unused.return":
            assert "b[1]" in parenthesized.splitlines()[finding.line - 1]


_GO_REBINDING_PLAIN = """package main

type Item struct{}

type Other struct{}

func (i Item) render() int { return 1 }

func (o Other) render() int { return 2 }

func main() {
	b := Item{}
	b = Other{}
	b.render()
}
"""

_GO_REBINDING_PARENTHESIZED = """package main

type Item struct{}

type Other struct{}

func (i Item) render() int { return 1 }

func (o Other) render() int { return 2 }

func main() {
	b := Item{}
	(b) = Other{}
	b.render()
}
"""

_JAVASCRIPT_REBINDING_PLAIN = """class Item { m() { return 1; } }
class Other { m() { return 2; } }
let b = new Item();
b = new Other();
b.m();
"""

_JAVASCRIPT_REBINDING_PARENTHESIZED = """class Item { m() { return 1; } }
class Other { m() { return 2; } }
let b = new Item();
(b) = new Other();
b.m();
"""

_PYTHON_REBINDING_PLAIN = """class Item:
    def m(self) -> int:
        return 1


class Other:
    def m(self) -> int:
        return 2


def run() -> None:
    b = Item()
    b = Other()
    b.m()
"""

_PYTHON_REBINDING_PARENTHESIZED = """class Item:
    def m(self) -> int:
        return 1


class Other:
    def m(self) -> int:
        return 2


def run() -> None:
    b = Item()
    (b) = Other()
    b.m()
"""


@pytest.mark.parametrize(
    ("language", "plain", "parenthesized", "expected"),
    [
        pytest.param(
            Language.GO,
            _GO_REBINDING_PLAIN,
            _GO_REBINDING_PARENTHESIZED,
            (("unused.function", 7, 15, "error"), ("unused.return", 14, 2, "warning")),
            id="go",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_REBINDING_PLAIN,
            _JAVASCRIPT_REBINDING_PARENTHESIZED,
            (("unused.function", 1, 14, "error"), ("unused.return", 5, 1, "warning")),
            id="javascript",
        ),
        pytest.param(
            Language.PYTHON,
            _PYTHON_REBINDING_PLAIN,
            _PYTHON_REBINDING_PARENTHESIZED,
            (("unused.function", 2, 9, "error"), ("unused.return", 14, 5, "warning")),
            id="python",
        ),
    ],
)
def test_parenthesized_rebinding_follows_the_assigned_value(
    language: Language,
    plain: str,
    parenthesized: str,
    expected: tuple[tuple[str, int, int, str], ...],
) -> None:
    parenthesized_findings = _findings(parenthesized, language)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in parenthesized_findings) == expected
    assert parenthesized_findings == _findings(plain, language)
    error = parenthesized_findings[0]
    assert error.severity == "error"
    assert "Other" not in parenthesized.splitlines()[error.line - 1]


_PYTHON_PARENTHESIZED_ELEMENT_INGRESS = """from vendor import fetch


class Item:
    def render(self) -> int:
        return 1


def run() -> None:
    items = [Item()]
    (items[0]) = fetch()
    items[1].render()
"""

_GO_PARENTHESIZED_ELEMENT_INGRESS = """package main

import "vendor"

type Item struct{}

func (i Item) render() int { return 1 }

func main() {
	items := []Item{{}}
	(items[0]) = vendor.Fetch()
	items[1].render()
}
"""

_JAVASCRIPT_PARENTHESIZED_ELEMENT_INGRESS = """import {fetch} from "vendor";
class Item { render() { return 1; } }
const items = [new Item()];
(items[0]) = fetch();
items[1].render();
"""

_TYPESCRIPT_PARENTHESIZED_ELEMENT_INGRESS = """import {fetch} from "vendor";
class Item { render(): number { return 1; } }
const items = [new Item()];
(items[0]) = fetch();
items[1].render();
"""


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        pytest.param(
            Language.PYTHON,
            _PYTHON_PARENTHESIZED_ELEMENT_INGRESS,
            (("type.boundary", 10, 5, "error"), ("unused.return", 12, 5, "warning")),
            id="python",
        ),
        pytest.param(
            Language.GO,
            _GO_PARENTHESIZED_ELEMENT_INGRESS,
            (("type.boundary", 10, 2, "error"), ("unused.return", 12, 2, "warning")),
            id="go",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_PARENTHESIZED_ELEMENT_INGRESS,
            (("type.boundary", 3, 7, "error"), ("unused.return", 5, 1, "warning")),
            id="javascript",
        ),
        pytest.param(
            Language.TYPESCRIPT,
            _TYPESCRIPT_PARENTHESIZED_ELEMENT_INGRESS,
            (("type.boundary", 3, 7, "error"), ("unused.return", 5, 1, "warning")),
            id="typescript",
        ),
    ],
)
def test_parenthesized_element_write_keeps_owner_and_restores_ingress(
    language: Language, code: str, expected: tuple[tuple[str, int, int, str], ...]
) -> None:
    findings = _findings(code, language, external=True)
    assert tuple((f.rule, f.line, f.column, f.severity) for f in findings) == expected
    assert not any(f.rule == "unused.function" for f in findings)
    assert findings[0].message == "Convert the third-party result into a typed object at ingress"
    assert "'render'" in findings[1].message


_PYTHON_SHADOW_CLASSES = """\
class Item:
    def render(self) -> int:
        return 1

class Other:
    def render(self) -> int:
        return 2
"""

_PYTHON_PARAMETER_SHADOW = (
    _PYTHON_SHADOW_CLASSES
    + """
def run(Item: type[Other]) -> None:
    xs = [Item()]
    xs[0].render()
"""
)

_PYTHON_CLASS_BINDING = (
    _PYTHON_SHADOW_CLASSES
    + """
def run() -> None:
    Item = Other
    xs = [Item()]
    xs[0].render()
"""
)

_PYTHON_SHADOW_WITH_UNUSED_METHOD = (
    _PYTHON_SHADOW_CLASSES
    + """
class Spare:
    def never(self) -> int:
        return 3

def run(Item: type[Other]) -> None:
    xs = [Item()]
    xs[0].render()
"""
)

_PYTHON_SPELLING_CONTROL = (
    _PYTHON_SHADOW_CLASSES
    + """
def run() -> None:
    xs = [Item()]
    xs[0].render()
"""
)

_JAVASCRIPT_SHADOW_CLASSES = """\
class Item {
    render() { return 1; }
}

class Other {
    render() { return 2; }
}
"""

_JAVASCRIPT_PARAMETER_SHADOW = (
    _JAVASCRIPT_SHADOW_CLASSES
    + """
export function run(Item) {
    const xs = [new Item()];
    xs[0].render();
}
"""
)

_JAVASCRIPT_VARIABLE_SHADOW = (
    _JAVASCRIPT_SHADOW_CLASSES
    + """
export function run() {
    const Item = Other;
    const xs = [new Item()];
    xs[0].render();
}
"""
)

_JAVASCRIPT_SPELLING_CONTROL = (
    _JAVASCRIPT_SHADOW_CLASSES
    + """
export function run() {
    const xs = [new Item()];
    xs[0].render();
}
"""
)

_TYPESCRIPT_PARAMETER_SHADOW = (
    _JAVASCRIPT_SHADOW_CLASSES
    + """
export function run(Item: typeof Other): void {
    const xs = [new Item()];
    xs[0].render();
}
"""
)

_TYPESCRIPT_VARIABLE_SHADOW = (
    _JAVASCRIPT_SHADOW_CLASSES
    + """
export function run(): void {
    const Item = Other;
    const xs = [new Item()];
    xs[0].render();
}
"""
)


def _evidence(
    code: str, language: Language, *, external: bool = False
) -> tuple[tuple[str, int, int, str, str], ...]:
    """Project findings onto their exact rule, anchor, severity and message."""
    return tuple(
        (finding.rule, finding.line, finding.column, finding.severity, finding.message)
        for finding in _findings(code, language, external=external)
    )


@pytest.mark.parametrize(
    ("language", "code"),
    [
        pytest.param(Language.PYTHON, _PYTHON_PARAMETER_SHADOW, id="python-parameter"),
        pytest.param(Language.JAVASCRIPT, _JAVASCRIPT_PARAMETER_SHADOW, id="javascript-parameter"),
        pytest.param(Language.JAVASCRIPT, _JAVASCRIPT_VARIABLE_SHADOW, id="javascript-variable"),
        pytest.param(Language.TYPESCRIPT, _TYPESCRIPT_PARAMETER_SHADOW, id="typescript-parameter"),
        pytest.param(Language.TYPESCRIPT, _TYPESCRIPT_VARIABLE_SHADOW, id="typescript-variable"),
        pytest.param(Language.TSX, _TYPESCRIPT_PARAMETER_SHADOW, id="tsx-parameter"),
        pytest.param(Language.TSX, _TYPESCRIPT_VARIABLE_SHADOW, id="tsx-variable"),
    ],
)
def test_shadowed_element_names_fall_back_to_the_unresolved_protection(
    language: Language, code: str
) -> None:
    """A declared non-class binding vetoes the spelled element type name (DESIGN §13.1)."""
    assert _evidence(code, language) == ()


def test_shadowed_element_name_protection_stays_scoped_to_the_unresolved_name() -> None:
    """The fallback protects the unresolved member name only, not every declaration."""
    assert _evidence(_PYTHON_SHADOW_WITH_UNUSED_METHOD, Language.PYTHON) == (
        (
            "unused.function",
            10,
            9,
            "error",
            "Function 'never' has no resolved read usage in the audited snapshots",
        ),
    )


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        pytest.param(
            Language.PYTHON,
            _PYTHON_SPELLING_CONTROL,
            (
                (
                    "unused.function",
                    6,
                    9,
                    "error",
                    "Function 'render' has no resolved read usage in the audited snapshots",
                ),
                ("unused.return", 11, 5, "warning", "Return value from 'render' is discarded"),
            ),
            id="python",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_SPELLING_CONTROL,
            (
                (
                    "unused.function",
                    6,
                    5,
                    "error",
                    "Function 'render' has no resolved read usage in the audited snapshots",
                ),
                ("unused.return", 11, 5, "warning", "Return value from 'render' is discarded"),
            ),
            id="javascript",
        ),
    ],
)
def test_unshadowed_element_names_keep_spelling_resolution(
    language: Language, code: str, expected: tuple[tuple[str, int, int, str, str], ...]
) -> None:
    """Without a lexical binding the spelled name still resolves the element type."""
    assert _evidence(code, language) == expected


def test_element_binding_to_a_class_keeps_the_frozen_spelling_result() -> None:
    """A variable bound to a class keeps the pre-fix spelling evidence for elements."""
    assert _evidence(_PYTHON_CLASS_BINDING, Language.PYTHON) == (
        (
            "unused.function",
            2,
            9,
            "error",
            "Function 'render' has no resolved read usage in the audited snapshots",
        ),
        ("unused.return", 12, 5, "warning", "Return value from 'render' is discarded"),
    )


_JAVASCRIPT_ELEMENT_CLASSES = """\
class Item {
    m() { return 1; }
}

class Other {
    m() { return 2; }
}

const items = [new Item()];
"""

_JAVASCRIPT_COMMENTED_PREFIX_ELEMENT_WRITE = (
    _JAVASCRIPT_ELEMENT_CLASSES + "(/* keep */ items[0]) = new Other();\nitems[1].m();\n"
)

_JAVASCRIPT_PARENTHESIZED_ELEMENT_WRITE = (
    _JAVASCRIPT_ELEMENT_CLASSES + "(items[0]) = new Other();\nitems[1].m();\n"
)

_JAVASCRIPT_PLAIN_ELEMENT_WRITE = (
    _JAVASCRIPT_ELEMENT_CLASSES + "items[0] = new Other();\nitems[1].m();\n"
)


@pytest.mark.parametrize(
    ("language", "commented", "parenthesized", "plain", "expected"),
    [
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_COMMENTED_PREFIX_ELEMENT_WRITE,
            _JAVASCRIPT_PARENTHESIZED_ELEMENT_WRITE,
            _JAVASCRIPT_PLAIN_ELEMENT_WRITE,
            (
                (
                    "unused.function",
                    6,
                    5,
                    "error",
                    "Function 'm' has no resolved read usage in the audited snapshots",
                ),
                ("unused.return", 11, 1, "warning", "Return value from 'm' is discarded"),
            ),
            id="javascript",
        ),
        pytest.param(
            Language.TYPESCRIPT,
            _JAVASCRIPT_COMMENTED_PREFIX_ELEMENT_WRITE,
            _JAVASCRIPT_PARENTHESIZED_ELEMENT_WRITE,
            _JAVASCRIPT_PLAIN_ELEMENT_WRITE,
            (
                (
                    "unused.function",
                    6,
                    5,
                    "error",
                    "Function 'm' has no resolved read usage in the audited snapshots",
                ),
                ("unused.return", 11, 1, "warning", "Return value from 'm' is discarded"),
            ),
            id="typescript",
        ),
    ],
)
def test_commented_element_write_matches_the_plain_controls(
    language: Language,
    commented: str,
    parenthesized: str,
    plain: str,
    expected: tuple[tuple[str, int, int, str, str], ...],
) -> None:
    """A comment before the element target is not a value carrier (DESIGN §13.2)."""
    assert _evidence(commented, language) == expected
    assert _evidence(parenthesized, language) == expected
    assert _evidence(plain, language) == expected


_JAVASCRIPT_INGRESS = """import {fetch} from "vendor";
const items = [0];
"""

_JAVASCRIPT_COMMENTED_ELEMENT_INGRESS = (
    _JAVASCRIPT_INGRESS + "(items[0] /* keep */) = fetch();\nconsole.log(items);\n"
)

_JAVASCRIPT_PARENTHESIZED_ELEMENT_INGRESS = (
    _JAVASCRIPT_INGRESS + "(items[0]) = fetch();\nconsole.log(items);\n"
)

_JAVASCRIPT_PLAIN_ELEMENT_INGRESS = (
    _JAVASCRIPT_INGRESS + "items[0] = fetch();\nconsole.log(items);\n"
)

_INGRESS_FINDING = (
    "type.boundary",
    2,
    7,
    "error",
    "Convert the third-party result into a typed object at ingress",
)


@pytest.mark.parametrize("language", [Language.JAVASCRIPT, Language.TYPESCRIPT])
def test_commented_element_ingress_write_restores_the_boundary_report(language: Language) -> None:
    """A comment after the element target keeps it in the writes evidence (DESIGN §13.2)."""
    expected = (_INGRESS_FINDING,)
    assert _evidence(_JAVASCRIPT_COMMENTED_ELEMENT_INGRESS, language, external=True) == expected
    assert _evidence(_JAVASCRIPT_PARENTHESIZED_ELEMENT_INGRESS, language, external=True) == expected
    assert _evidence(_JAVASCRIPT_PLAIN_ELEMENT_INGRESS, language, external=True) == expected


_GO_MAP_TYPE_CLASSES = """\
package sample

type key struct{}

type item struct{}

func (k key) render() int { return 1 }

func (i item) render() int { return 2 }
"""

_GO_COMMENTED_POINTER_MAP_ANNOTATION = (
    _GO_MAP_TYPE_CLASSES
    + """
var xs []* /* keep */ map[key]item

func Run() {
\txs[0]["k"].render()
}
"""
)

_GO_PARENTHESIZED_POINTER_MAP_ANNOTATION = (
    _GO_MAP_TYPE_CLASSES
    + """
var xs []*(map[key]item)

func Run() {
\txs[0]["k"].render()
}
"""
)

_GO_POINTER_MAP_ANNOTATION = (
    _GO_MAP_TYPE_CLASSES
    + """
var xs []*map[key]item

func Run() {
\txs[0]["k"].render()
}
"""
)

_GO_POINTER_MAP_FINDINGS = (
    (
        "unused.function",
        7,
        14,
        "error",
        "Function 'render' has no resolved read usage in the audited snapshots",
    ),
    ("unused.return", 14, 2, "warning", "Return value from 'render' is discarded"),
)


@pytest.mark.parametrize(
    "code",
    [
        pytest.param(_GO_COMMENTED_POINTER_MAP_ANNOTATION, id="comment"),
        pytest.param(_GO_PARENTHESIZED_POINTER_MAP_ANNOTATION, id="type-parentheses"),
        pytest.param(_GO_POINTER_MAP_ANNOTATION, id="control"),
    ],
)
def test_go_commented_pointer_map_annotations_reduce_to_the_value_type(code: str) -> None:
    """Annotation reduction skips comments and transparent type parentheses (§13.3)."""
    assert _evidence(code, Language.GO) == _GO_POINTER_MAP_FINDINGS


_GO_COMMENTED_POINTER_MAP_VALUE = (
    _GO_MAP_TYPE_CLASSES
    + """
func Run() {
\txs := []* /* keep */ map[key]item{{}}
\txs[0]["k"].render()
}
"""
)

_GO_POINTER_MAP_VALUE = (
    _GO_MAP_TYPE_CLASSES
    + """
func Run() {
\txs := []*map[key]item{{}}
\txs[0]["k"].render()
}
"""
)


def test_go_commented_value_types_reduce_to_the_value_type() -> None:
    """The composite literal type follows the same reduction as the annotation path."""
    expected = (
        (
            "unused.function",
            7,
            14,
            "error",
            "Function 'render' has no resolved read usage in the audited snapshots",
        ),
        ("unused.return", 13, 2, "warning", "Return value from 'render' is discarded"),
    )
    assert _evidence(_GO_COMMENTED_POINTER_MAP_VALUE, Language.GO) == expected
    assert _evidence(_GO_POINTER_MAP_VALUE, Language.GO) == expected


_GO_ITEM_TYPE = """\
package sample

type item struct{}

func (i item) render() int { return 2 }
"""

_GO_POINTER_ITEM_TYPE = """\
package sample

type item struct{}

func (i *item) render() int { return 2 }
"""

_GO_COMMENTED_MAKE = (
    _GO_ITEM_TYPE
    + """
func Run() {
\txs := make(/* keep */ []item, 1)
\txs[0].render()
}
"""
)

_GO_PLAIN_MAKE = (
    _GO_ITEM_TYPE
    + """
func Run() {
\txs := make([]item, 1)
\txs[0].render()
}
"""
)

_GO_COMMENTED_NEW = (
    _GO_POINTER_ITEM_TYPE
    + """
func Run() {
\tp := new(/* keep */ item)
\tp.render()
}
"""
)

_GO_PLAIN_NEW = (
    _GO_POINTER_ITEM_TYPE
    + """
func Run() {
\tp := new(item)
\tp.render()
}
"""
)

_DISCARDED_RENDER = (("unused.return", 9, 2, "warning", "Return value from 'render' is discarded"),)


@pytest.mark.parametrize(
    ("commented", "plain"),
    [
        pytest.param(_GO_COMMENTED_MAKE, _GO_PLAIN_MAKE, id="make"),
        pytest.param(_GO_COMMENTED_NEW, _GO_PLAIN_NEW, id="new"),
    ],
)
def test_go_builtin_type_arguments_ignore_comments(commented: str, plain: str) -> None:
    """A comment must not become the make/new type argument, so the warning survives."""
    assert _evidence(commented, Language.GO) == _DISCARDED_RENDER
    assert _evidence(plain, Language.GO) == _DISCARDED_RENDER


_GO_PARENTHESIZED_MAKE_TYPE = (
    _GO_MAP_TYPE_CLASSES
    + """
func Run() {
\tm := make((map[key]item), 1)
\tm["k"].render()
}
"""
)

_GO_PLAIN_MAKE_TYPE = (
    _GO_MAP_TYPE_CLASSES
    + """
func Run() {
\tm := make(map[key]item, 1)
\tm["k"].render()
}
"""
)


def test_go_builtin_type_argument_traverses_transparent_type_parentheses() -> None:
    """A parenthesized make type still reduces to the map value type (§13.3)."""
    expected = (
        (
            "unused.function",
            7,
            14,
            "error",
            "Function 'render' has no resolved read usage in the audited snapshots",
        ),
        ("unused.return", 13, 2, "warning", "Return value from 'render' is discarded"),
    )
    assert _evidence(_GO_PARENTHESIZED_MAKE_TYPE, Language.GO) == expected
    assert _evidence(_GO_PLAIN_MAKE_TYPE, Language.GO) == expected


_GO_POINTER_DEREFERENCE_WRITE = """\
package main

type item struct{}

type other struct{}

func (i item) m() {}

func (o other) m() {}

func main() {
\tp := &item{}
\t*p = other{}
\tp.m()
}
"""


def test_pointer_dereference_write_pins_the_registered_overwrite() -> None:
    """Pin the registered pointer-dereference overwrite (PROJECT §10.6, DESIGN §13.3)."""
    assert _evidence(_GO_POINTER_DEREFERENCE_WRITE, Language.GO) == (
        (
            "unused.function",
            7,
            15,
            "error",
            "Function 'm' has no resolved read usage in the audited snapshots",
        ),
    )


_PYTHON_THIRD_PARTY_THEN_PLAIN_WRITE = """\
import vendor


def run() -> None:
    items = [0]
    items[0] = vendor.fetch()
    items[0] = 1
    print(items)
"""

_JAVASCRIPT_THIRD_PARTY_THEN_PLAIN_WRITE = """\
import {fetch} from "vendor";
const items = [0];
items[0] = fetch();
items[0] = 1;
console.log(items);
"""


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        pytest.param(
            Language.PYTHON,
            _PYTHON_THIRD_PARTY_THEN_PLAIN_WRITE,
            (
                "type.boundary",
                5,
                5,
                "error",
                "Convert the third-party result into a typed object at ingress",
            ),
            id="python",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_THIRD_PARTY_THEN_PLAIN_WRITE,
            _INGRESS_FINDING,
            id="javascript",
        ),
    ],
)
def test_third_party_element_write_before_a_plain_write_still_reports(
    language: Language, code: str, expected: tuple[str, int, int, str, str]
) -> None:
    """A later plain element write does not erase the third-party ingress evidence."""
    assert _evidence(code, language, external=True) == (expected,)


_PYTHON_COMMENTED_VALUE_REBINDING = """\
class Item:
    def m(self) -> int:
        return 1


class Other:
    def m(self) -> int:
        return 2


def run() -> None:
    b = Item()
    b = (  # keep
        Other())
    b.m()
"""

_PYTHON_UNCOMMENTED_VALUE_REBINDING = _PYTHON_COMMENTED_VALUE_REBINDING.replace("  # keep", "")

_JAVASCRIPT_COMMENTED_VALUE_REBINDING = """\
class Item { m() { return 1; } }
class Other { m() { return 2; } }
let b = new Item();
b = (/* keep */ new Other());
b.m();
"""

_JAVASCRIPT_UNCOMMENTED_VALUE_REBINDING = _JAVASCRIPT_COMMENTED_VALUE_REBINDING.replace(
    "/* keep */ ", ""
)


@pytest.mark.parametrize(
    ("language", "commented", "control", "expected"),
    [
        pytest.param(
            Language.PYTHON,
            _PYTHON_COMMENTED_VALUE_REBINDING,
            _PYTHON_UNCOMMENTED_VALUE_REBINDING,
            (
                (
                    "unused.function",
                    2,
                    9,
                    "error",
                    "Function 'm' has no resolved read usage in the audited snapshots",
                ),
                ("unused.return", 15, 5, "warning", "Return value from 'm' is discarded"),
            ),
            id="python",
        ),
        pytest.param(
            Language.JAVASCRIPT,
            _JAVASCRIPT_COMMENTED_VALUE_REBINDING,
            _JAVASCRIPT_UNCOMMENTED_VALUE_REBINDING,
            (
                (
                    "unused.function",
                    1,
                    14,
                    "error",
                    "Function 'm' has no resolved read usage in the audited snapshots",
                ),
                ("unused.return", 5, 1, "warning", "Return value from 'm' is discarded"),
            ),
            id="javascript",
        ),
    ],
)
def test_commented_rebinding_values_match_the_uncommented_controls(
    language: Language,
    commented: str,
    control: str,
    expected: tuple[tuple[str, int, int, str, str], ...],
) -> None:
    """A comment inside a rebinding value's parentheses is not a value carrier (§13.2)."""
    assert _evidence(commented, language) == expected
    assert _evidence(control, language) == expected


def test_cross_file_value_inferred_elements_resolve_the_imported_class(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An imported class keeps element resolution while the unused control still reports."""
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "models.py").write_text(
        "class Item:\n"
        "    def render(self) -> int:\n"
        "        return 1\n"
        "\n"
        "\n"
        "class Spare:\n"
        "    def never(self) -> int:\n"
        "        return 2\n"
    )
    (tmp_path / "app.py").write_text("from models import Item\n\nxs = [Item()]\nxs[0].render()\n")
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.rule, f.severity) for f in report.findings] == [
        ("app.py", 4, "unused.return", "warning"),
        ("models.py", 7, "unused.function", "error"),
    ]
    assert "render" in report.findings[0].message
    assert "never" in report.findings[1].message
