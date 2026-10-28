"""Checker settings isolate enforcement while preserving shared analysis and scope."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from code_harness.cli import main
from code_harness.diagnostics import Report
from code_harness.engine import check
from code_harness.plugins.builtins import builtin_analyzers
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


@pytest.mark.parametrize(
    ("checker", "code", "options"),
    [
        ("size.lines", "def run() -> None:\n    pass\n", ',"lines":1'),
        ("size.statements", "def run() -> None:\n    first()\n    second()\n", ',"statements":1'),
        (
            "size.complexity",
            "def run(value: bool) -> None:\n    if value:\n        run(False)",
            ',"complexity":1',
        ),
        (
            "size.nesting",
            "def run(value: bool) -> None:\n    if value:\n        while value:\n            break",
            ',"nesting":1',
        ),
        ("size.parameters", "def run(a: int, b: int) -> int:\n    return a + b", ',"parameters":1'),
        ("type.annotation", "def run(value: object) -> None:\n    pass", ""),
        ("type.signature", "def run(value):\n    return value", ""),
        ("type.broad", "from typing import Any\nvalue: Any", ""),
        ("type.broad", "import json\nvalue = json.dumps({'count': 1})", ""),
        ("type.assertion", "from typing import cast\nvalue = cast(int, raw)", ""),
        ("type.suppression", "# type: ignore\nvalue: int = 1", ""),
        ("imports.wildcard", "from example import *", ""),
        (
            "architecture.owner",
            "value: int = 1",
            ',"owners":[{"name":"other","paths":["other/*"]}]',
        ),
        (
            "architecture.import",
            "import forbidden",
            ',"boundaries":[{"name":"no forbidden","sources":["*"],'
            '"forbidden_imports":["forbidden"]}]',
        ),
        (
            "architecture.structure",
            "value: int = 1",
            ',"placements":[{"name":"owned modules","paths":["*"],"allowed_paths":["domain/*"]}]',
        ),
        ("architecture.dispatch", 'if language == "python":\n    run()', ""),
        (
            "architecture.object_model",
            'def run() -> None:\n    if language == "python":\n        run()',
            ',"paths":["*"]',
        ),
    ],
)
def test_disabling_one_checker_preserves_other_findings(
    checker: str, code: str, options: str
) -> None:
    source = Source("app.py", code.encode(), Language.PYTHON)
    key = "function_size" if checker.startswith("size.") else checker
    policy_json = f'{{"checkers":{{"{key}":{{"enabled":true{options}}}}}}}'
    enabled = Policy.model_validate_json(policy_json)
    disabled = Policy.model_validate_json(policy_json.replace('"enabled":true', '"enabled":false'))
    findings = check(source, enabled)
    assert any(finding.rule == checker for finding in findings)
    assert check(source, disabled) == tuple(f for f in findings if f.rule != checker)


@pytest.mark.parametrize(
    "document",
    [
        '{"version":1}',
        '{"limits":{"lines":50}}',
        '{"owners":[]}',
        '{"boundaries":[]}',
        '{"class_modules":[]}',
        '{"checkers":{"typo.checker":{}}}',
        '{"checkers":{"type.erasure":{"enabled":false}}}',
        '{"checkers":{"type.broad":{"enabled":"false"}}}',
        '{"checkers":{"type.broad":{"enabled":0}}}',
        '{"checkers":{"type.broad":{"maximum":1}}}',
        '{"checkers":{"function_size":{"lines":0}}}',
        '{"checkers":{"function_size":{"lines":true}}}',
        '{"checkers":{"function_size":{"lines":"50"}}}',
        '{"checkers":{"architecture.owner":{"paths":["*"]}}}',
        '{"checkers":{"architecture.object_model":{"owners":[]}}}',
        '{"checkers":{"type.signature":{"exclude":["*"]}}}',
        '{"checkers":{"type.signature":{"include":["*"]}}}',
    ],
)
def test_invalid_or_misplaced_checker_options_are_rejected(document: str) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate_json(document)


def test_partial_options_preserve_other_metric_defaults() -> None:
    policy = Policy.model_validate_json('{"checkers":{"function_size":{"complexity":2}}}')
    options = policy.checkers
    assert options.function_size.lines == 50
    assert options.function_size.statements == 50
    assert options.function_size.complexity == 2
    assert options.function_size.nesting == 3
    assert options.function_size.parameters == 5
    assert options.function_size.enabled
    assert options.disabled_rules() == frozenset()
    assert Policy().checkers.disabled_rules() == frozenset()


def test_syntax_is_not_a_configurable_checker() -> None:
    assert "syntax.invalid" not in builtin_analyzers()[0].rule_ids
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Policy.model_validate_json('{"checkers":{"syntax.invalid":{"enabled":false}}}')


def test_global_scope_and_disabled_checkers_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text(
        '{"include":["*.py"],"exclude":["excluded.py"],'
        '"checkers":{"type.signature":{"enabled":false}}}'
    )
    (tmp_path / "app.py").write_text("def run(value):\n    return value")
    (tmp_path / "excluded.py").write_text("def broken(:")
    (tmp_path / "outside.ts").write_text("type Payload = any;")
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.files == 1
    assert report.findings == ()
    assert report.disabled_checkers == ("type.signature",)
    assert main(["--root", str(tmp_path), "--all"]) == 0
    assert "Disabled checkers: type.signature" in capsys.readouterr().out


def test_disabling_all_analyzer_rules_skips_parsing() -> None:
    analyzer = builtin_analyzers()[0]
    names = ("function_size", *(name for name in analyzer.rule_ids if not name.startswith("size.")))
    settings = ",".join(f'"{name}":{{"enabled":false}}' for name in names)
    policy = Policy.model_validate_json('{"checkers":{' + settings + "}}")
    source = Source("app.py", b"def broken(:", Language.PYTHON)
    assert analyzer.analyze(source, policy) == ()
    assert check(source, policy) == ()


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.GO, "package demo\ntype Payload interface{}"),
        (Language.TYPESCRIPT, "type Payload = any; const result = value as Result;"),
        (Language.TSX, "type Payload = any; const result = value as Result;"),
    ],
)
def test_shared_type_checker_flag_applies_across_languages(language: Language, code: str) -> None:
    source = Source("example", code.encode(), language)
    enabled = check(source, Policy())
    policy = Policy.model_validate_json('{"checkers":{"type.broad":{"enabled":false}}}')
    assert any(finding.rule == "type.broad" for finding in enabled)
    assert check(source, policy) == tuple(f for f in enabled if f.rule != "type.broad")


def test_function_size_switch_disables_all_metrics_and_preserves_type_checks() -> None:
    source = Source(
        "app.py",
        b"def run(first, second):\n    if first:\n        while second:\n"
        b"            first -= 1\n    return first\n",
        Language.PYTHON,
    )
    policy_json = (
        '{"checkers":{"function_size":{"lines":1,"statements":1,'
        '"complexity":1,"nesting":1,"parameters":1}}}'
    )
    findings = check(source, Policy.model_validate_json(policy_json))
    metric_ids = {
        "size.lines",
        "size.statements",
        "size.complexity",
        "size.nesting",
        "size.parameters",
    }
    assert {finding.rule for finding in findings} == metric_ids | {"type.signature"}
    disabled = Policy.model_validate_json(
        policy_json.replace('"lines":1', '"enabled":false,"lines":1')
    )
    assert disabled.checkers.disabled_rules() == metric_ids
    assert check(source, disabled) == tuple(f for f in findings if f.rule == "type.signature")


def test_function_size_disabled_report_uses_the_checker_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"function_size":{"enabled":false,"lines":1}}}'
    )
    (tmp_path / "app.py").write_text("def run() -> int:\n    return 1\n")
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.disabled_checkers == ("function_size",)
    assert report.findings == ()
    assert main(["--root", str(tmp_path), "--all"]) == 0
    assert "Disabled checkers: function_size" in capsys.readouterr().out


@pytest.mark.parametrize(
    "dimension", ["lines", "statements", "complexity", "nesting", "parameters"]
)
def test_individual_metric_checker_entries_are_rejected(dimension: str) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate_json(f'{{"checkers":{{"size.{dimension}":{{"maximum":50}}}}}}')
