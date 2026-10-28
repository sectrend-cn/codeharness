"""Read-only projection diagnostics in full, changed-definition and index snapshots."""

import subprocess
from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Report

_PROJECTION = """export function project(source, target) {
    if (source.a !== undefined) target.x = source.a;
    if (source.b !== undefined) target.y = source.b;
    if (source.c !== undefined) target.z = source.c;
    return target;
}
"""


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(("git", "-C", str(root), *arguments), check=True, capture_output=True)


@pytest.fixture
def projection_repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "projection@example.invalid")
    _git(tmp_path, "config", "user.name", "Projection Test")
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}\n")
    (tmp_path / "app.ts").write_text("export function project() { return {}; }\n")
    _git(tmp_path, "add", ".codeharness/code-harness.json", "app.ts")
    _git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


@pytest.mark.parametrize("mode", [("--all",), ("--base", "HEAD"), ("--staged",)])
def test_projection_cli_modes_preserve_source_policy_and_index(
    projection_repository: Path, capsys: pytest.CaptureFixture[str], mode: tuple[str, ...]
) -> None:
    root = projection_repository
    source = root / "app.ts"
    source.write_text(_PROJECTION)
    _git(root, "add", "app.ts")
    source.write_text(_PROJECTION + "\nexport const unstaged = 1;\n")
    policy = root / ".codeharness/code-harness.json"
    index = root / ".git/index"
    before = (source.read_bytes(), policy.read_bytes(), index.read_bytes())
    assert main(["--root", str(root), *mode, "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    findings = tuple(f for f in report.findings if f.rule == "structure.guarded_projection")
    assert len(findings) == 1
    assert (findings[0].path, findings[0].line, findings[0].column) == ("app.ts", 2, 5)
    assert "3 guarded field projections" in findings[0].message
    assert before == (source.read_bytes(), policy.read_bytes(), index.read_bytes())


def test_changed_definition_reports_cluster_when_only_last_guard_changes(
    projection_repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = projection_repository
    source = root / "app.ts"
    source.write_text(_PROJECTION.replace("target.z = source.c", "target.z = transform(source.c)"))
    _git(root, "add", "app.ts")
    _git(root, "commit", "-qm", "two candidates")
    source.write_text(_PROJECTION)
    assert main(["--root", str(root), "--base", "HEAD", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert len(report.findings) == 1
    assert report.findings[0].rule == "structure.guarded_projection"
    assert report.findings[0].line == 2


def test_staged_projection_uses_index_despite_different_working_source(
    projection_repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = projection_repository
    source = root / "app.ts"
    source.write_text(_PROJECTION)
    _git(root, "add", "app.ts")
    source.write_text("export const working = 1;\n")
    before = source.read_bytes()
    assert main(["--root", str(root), "--staged", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert any(f.rule == "structure.guarded_projection" for f in report.findings)
    assert source.read_bytes() == before


def test_disabled_projection_is_reported_by_cli(
    projection_repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = projection_repository
    (root / "app.ts").write_text(_PROJECTION)
    (root / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"structure.guarded_projection":{"enabled":false}}}'
    )
    assert main(["--root", str(root), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.findings == ()
    assert report.disabled_checkers == ("structure.guarded_projection",)
