"""Source placement follows declared feature ownership across source snapshots."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from code_harness.cli import main
from code_harness.diagnostics import Report
from code_harness.engine import check
from code_harness.policy.models import (
    Checkers,
    ImportOptions,
    Owner,
    OwnershipOptions,
    Policy,
    SourcePlacement,
    StructureOptions,
)
from code_harness.source import Language, Source

_PLACEMENT = SourcePlacement(
    name="language rule modules",
    paths=("src/*_rules.*",),
    allowed_paths=("src/languages/*", "src/extensions/*"),
)
_OPTIONS = StructureOptions(placements=(_PLACEMENT,))
_POLICY = Policy(checkers=Checkers(architecture_structure=_OPTIONS))


@pytest.mark.parametrize(
    ("language", "suffix", "code"),
    [
        (Language.PYTHON, "py", "value: int = 1\n"),
        (Language.GO, "go", "package sample\n"),
        (Language.JAVASCRIPT, "js", "const value = 1;\n"),
        (Language.TYPESCRIPT, "ts", "const value: number = 1;\n"),
        (Language.TSX, "tsx", "const value = <div />;\n"),
    ],
)
def test_misplaced_sources_fail_across_languages(
    language: Language, suffix: str, code: str
) -> None:
    source = Source(f"src/feature_rules.{suffix}", code.encode(), language)
    findings = check(source, _POLICY)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule == "architecture.structure"
    assert finding.path == source.path
    assert (finding.line, finding.column, finding.severity) == (1, 1, "error")
    assert "language rule modules" in finding.message
    assert "src/languages/*" in finding.message


@pytest.mark.parametrize(
    ("path", "misplaced"),
    [
        ("src/languages/python_rules.py", False),
        ("src/languages/python/type_rules.py", False),
        ("src/extensions/python_rules.py", False),
        ("src/languages_extra/python_rules.py", True),
        ("src/shared/python_rules.py", True),
        ("src/Languages/python_rules.py", True),
        ("src/unrelated.py", False),
    ],
)
def test_placement_matches_exact_configured_patterns(path: str, misplaced: bool) -> None:
    findings = check(Source(path, b"value: int = 1\n", Language.PYTHON), _POLICY)
    assert bool(findings) is misplaced


def test_valid_owner_and_disabled_imports_do_not_hide_bad_placement() -> None:
    policy = Policy(
        checkers=Checkers(
            architecture_structure=_OPTIONS,
            architecture_owner=OwnershipOptions(owners=(Owner(name="shared", paths=("*",)),)),
            architecture_import=ImportOptions(enabled=False),
        )
    )
    findings = check(Source("src/python_rules.py", b"value: int = 1", Language.PYTHON), policy)
    assert [finding.rule for finding in findings] == ["architecture.structure"]


def test_each_matching_placement_is_required() -> None:
    other = SourcePlacement(name="plugin modules", paths=("*",), allowed_paths=("src/plugins/*",))
    policy = Policy(
        checkers=Checkers(architecture_structure=StructureOptions(placements=(_PLACEMENT, other)))
    )
    source = Source("src/python_rules.py", b"value: int = 1", Language.PYTHON)
    findings = check(source, policy)
    assert len(findings) == 2
    assert all(finding.rule == "architecture.structure" for finding in findings)
    assert check(source, Policy()) == ()


@pytest.mark.parametrize(
    "settings",
    [
        '{"placements":[{"name":"rules","paths":[],"allowed_paths":["src/*"]}]}',
        '{"placements":[{"name":"rules","paths":["*"],"allowed_paths":[]}]}',
        '{"placements":[{"name":"","paths":["*"],"allowed_paths":["src/*"]}]}',
        '{"placements":[{"name":"rules","paths":["*"]}]}',
        '{"placements":[] ,"enabled":"false"}',
        '{"paths":["*"]}',
    ],
)
def test_invalid_placement_configuration_fails_closed(settings: str) -> None:
    with pytest.raises(ValidationError):
        Policy.model_validate_json('{"checkers":{"architecture.structure":' + settings + "}}")


def test_repository_policy_rejects_python_rules_outside_language_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = Policy.model_validate_json((root / ".codeharness/code-harness.json").read_bytes())
    old = Source("src/code_harness/python_rules.py", b"value: int = 1", Language.PYTHON)
    moved = Source("src/code_harness/languages/python_rules.py", old.content, Language.PYTHON)
    assert any(finding.rule == "architecture.structure" for finding in check(old, policy))
    assert check(moved, policy) == ()


def test_cli_reports_and_can_disable_structure_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    policy_path = tmp_path / ".codeharness/code-harness.json"
    policy_path.write_text(_POLICY.model_dump_json(by_alias=True))
    (tmp_path / "src").mkdir()
    source = tmp_path / "src/python_rules.py"
    source.write_text("value: int = 1\n")
    original = source.read_bytes()
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [finding.rule for finding in report.findings] == ["architecture.structure"]
    policy_path.write_text('{"checkers":{"architecture.structure":{"enabled":false}}}')
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.disabled_checkers == ("architecture.structure",)
    assert source.read_bytes() == original


def test_invalid_syntax_still_reports_misplaced_source(caplog: pytest.LogCaptureFixture) -> None:
    source = Source("src/python_rules.py", b"def broken(:", Language.PYTHON)
    findings = check(source, _POLICY)
    assert any(finding.rule == "architecture.structure" for finding in findings)
    assert "syntax warning" in caplog.text
