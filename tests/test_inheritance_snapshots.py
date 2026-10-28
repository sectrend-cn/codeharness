"""Inherited usage is rebuilt from the selected full, changed or index snapshots."""

import subprocess
from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Report

_BASE = (
    "export abstract class Base {\n"
    " render(): string { return this.hook(); }\n"
    " protected abstract hook(): string;\n}\n"
)
_MIDDLE = (
    'import { Base } from "./base";\n'
    "export abstract class Middle<T> extends Base {\n"
    " render(): string { return super.render(); }\n}\n"
)
_LEAF = (
    'import { Base } from "./base";\n'
    'import { Middle } from "./middle";\n'
    "class Leaf extends Middle<string> {\n"
    " protected hook(): string { return 'used'; }\n}\n"
    "function create(): Base { return new Leaf(); }\n"
    "export function execute(): string { return create().render(); }\n"
)


def _git(root: Path, *arguments: str) -> None:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments), capture_output=True, text=True, check=True
    )
    assert result.returncode == 0


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "gate@example.invalid")
    _git(tmp_path, "config", "user.name", "Gate Test")
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}\n")
    (tmp_path / "base.ts").write_text(_BASE)
    (tmp_path / "middle.ts").write_text(_MIDDLE)
    (tmp_path / "leaf.ts").write_text(_LEAF.replace("'used'", "'initial'"))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "initial inheritance contracts")
    (tmp_path / "leaf.ts").write_text(_LEAF)
    _git(tmp_path, "add", "leaf.ts")
    return tmp_path


@pytest.mark.parametrize("mode", [("--all",), ("--base", "HEAD"), ("--staged",)])
def test_imported_inherited_usage_is_available_in_every_snapshot_mode(
    repository: Path, capsys: pytest.CaptureFixture[str], mode: tuple[str, ...]
) -> None:
    assert main(["--root", str(repository), *mode, "--format", "json"]) == 0
    assert Report.model_validate_json(capsys.readouterr().out).findings == ()


@pytest.mark.parametrize("changed", ["base.ts", "middle.ts", "leaf.ts"])
def test_unstaged_dispatch_changes_do_not_contaminate_index_evidence(
    repository: Path, capsys: pytest.CaptureFixture[str], changed: str
) -> None:
    replacements = {
        "base.ts": _BASE.replace("this.hook()", "'constant'"),
        "middle.ts": _MIDDLE.replace("extends Base", ""),
        "leaf.ts": _LEAF.replace("hook():", "unused():"),
    }
    (repository / changed).write_text(replacements[changed])
    preserved = (repository / changed).read_bytes()
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    assert Report.model_validate_json(capsys.readouterr().out).findings == ()
    assert main(["--root", str(repository), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.column, f.rule) for f in report.findings] == [
        ("leaf.ts", 4, 12, "unused.function")
    ]
    assert (repository / changed).read_bytes() == preserved


def test_staging_a_changed_base_invalidates_previous_dispatch_evidence(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    assert Report.model_validate_json(capsys.readouterr().out).findings == ()
    (repository / "base.ts").write_text(_BASE.replace("this.hook()", "'constant'"))
    _git(repository, "add", "base.ts")
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.rule) for f in report.findings] == [
        ("leaf.ts", 4, "unused.function")
    ]
