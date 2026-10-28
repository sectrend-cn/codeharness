"""Policy rejects procedural extension points and language identity dispatch."""

from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.engine import check
from code_harness.policy.models import Checkers, ObjectModelOptions, Policy
from code_harness.source import Language, Source


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "if source.language == Language.GO:\n    run()\n"),
        (Language.PYTHON, "if language in {Language.GO, Language.PYTHON}:\n    run()\n"),
        (Language.PYTHON, "match source.language:\n    case Language.GO:\n        run()\n"),
        (Language.PYTHON, "if rule_id == 'type.broad':\n    run()\n"),
        (Language.GO, 'package demo\nfunc Run(language string) { if language == "go" { run() } }'),
        (
            Language.GO,
            'package demo\nfunc Run(language string) { switch language { case "go": run() } }',
        ),
        (Language.JAVASCRIPT, 'if (source.language === "python") { run(); }'),
        (Language.TYPESCRIPT, 'switch (source.language) { case "python": run(); }'),
        (Language.TSX, 'if (rule_id === "custom") { run(); }'),
    ],
)
def test_identity_dispatch_is_rejected(language: Language, code: str) -> None:
    findings = check(Source("extension", code.encode(), language), Policy())
    assert any(finding.rule == "architecture.dispatch" for finding in findings)


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (Language.PYTHON, "def check(value: int) -> int:\n    return value\n"),
        (Language.PYTHON, "@decorate\ndef check(value: int) -> int:\n    return value\n"),
        (Language.GO, "package demo\nfunc Check(value int) int { return value }"),
        (Language.JAVASCRIPT, "export function check(value) { return value; }"),
        (Language.TYPESCRIPT, "export const check = (value: number): number => value;"),
    ],
)
def test_configured_extensions_require_class_ownership(language: Language, code: str) -> None:
    source = Source("extensions/check", code.encode(), language)
    assert check(source, Policy()) == ()
    findings = check(
        source,
        Policy(
            checkers=Checkers(architecture_object_model=ObjectModelOptions(paths=("extensions/*",)))
        ),
    )
    assert [finding.rule for finding in findings] == ["architecture.object_model"]


@pytest.mark.parametrize(
    ("language", "code"),
    [
        (
            Language.PYTHON,
            "class Rule:\n    def check(self, value: int) -> int:\n        return value\n",
        ),
        (Language.PYTHON, "def _pure(value: int) -> int:\n    return value + 1\n"),
        (
            Language.GO,
            "package demo\ntype Rule struct{}\nfunc (r Rule) Check(value int) int { return value }",
        ),
        (Language.TYPESCRIPT, "class Rule { check(value: number): number { return value; } }"),
        (Language.PYTHON, "if source.language != self.definition.language:\n    reject()\n"),
    ],
)
def test_methods_helpers_and_compatibility_guards_pass(language: Language, code: str) -> None:
    findings = check(
        Source("extension", code.encode(), language),
        Policy(checkers=Checkers(architecture_object_model=ObjectModelOptions(paths=("*",)))),
    )
    assert not any(finding.rule.startswith("architecture.") for finding in findings)


def test_cli_enforces_class_policy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text(
        '{"version": 2, "checkers": {"architecture.object_model": {"paths": ["rules.py"]}}}'
    )
    (tmp_path / "rules.py").write_text("def check() -> None:\n    pass\n")
    assert main(["--root", str(tmp_path), "--all"]) == 1
    assert "architecture.object_model" in capsys.readouterr().out
