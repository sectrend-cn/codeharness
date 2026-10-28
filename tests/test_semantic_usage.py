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
