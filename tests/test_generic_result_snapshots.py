"""Generic inference uses imported contracts from the selected immutable Git view."""

import subprocess
from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import Report

_LIBRARY = "export class State {\n transaction<R>(work: () => R): R { return work(); }\n}\n"
_CALLBACK = "function effect(): void {}\nexport function callback() { return effect(); }\n"
_CLIENT = (
    'import { State } from "./library";\n'
    'import { callback } from "./callback";\n'
    "const state = new State();\n"
    "state.transaction(callback);\n"
    "state.transaction(() => 42);\n"
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
    (tmp_path / "library.ts").write_text(_LIBRARY)
    (tmp_path / "callback.ts").write_text(_CALLBACK)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "initial contracts")
    (tmp_path / "client.ts").write_text(_CLIENT)
    _git(tmp_path, "add", "client.ts")
    return tmp_path


@pytest.mark.parametrize("mode", [("--all",), ("--base", "HEAD"), ("--staged",)])
def test_imported_method_and_callback_share_snapshot_ownership(
    repository: Path, capsys: pytest.CaptureFixture[str], mode: tuple[str, ...]
) -> None:
    assert main(["--root", str(repository), *mode, "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.column, f.rule) for f in report.findings] == [
        ("client.ts", 5, 1, "unused.return")
    ]


@pytest.mark.parametrize("changed", ["library.ts", "callback.ts"])
def test_staged_inference_ignores_unstaged_signatures_and_bodies(
    repository: Path, capsys: pytest.CaptureFixture[str], changed: str
) -> None:
    replacement = {
        "library.ts": _LIBRARY.replace(": R { return work(); }", ": number { work(); return 1; }"),
        "callback.ts": "export function callback(): number { return 1; }\n",
    }
    (repository / changed).write_text(replacement[changed])
    before = (repository / changed).read_bytes()
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    staged = Report.model_validate_json(capsys.readouterr().out)
    assert [f.line for f in staged.findings if f.rule == "unused.return"] == [5]
    assert main(["--root", str(repository), "--all", "--format", "json"]) == 0
    working = Report.model_validate_json(capsys.readouterr().out)
    assert [f.line for f in working.findings if f.path == "client.ts"] == [4, 5]
    assert (repository / changed).read_bytes() == before


def test_staged_signature_change_invalidates_previous_result_evidence(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    before = Report.model_validate_json(capsys.readouterr().out)
    assert [f.line for f in before.findings] == [5]
    (repository / "callback.ts").write_text("export function callback(): number { return 1; }\n")
    _git(repository, "add", "callback.ts")
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    after = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line) for f in after.findings] == [("client.ts", 4), ("client.ts", 5)]


def test_python_imported_generic_method_and_callback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "library.py").write_text(
        "from typing import Callable\nclass State:\n"
        "    def transaction[R](self, work: Callable[[], R]) -> R:\n        return work()\n"
    )
    (tmp_path / "callback.py").write_text("def callback() -> None:\n    pass\n")
    (tmp_path / "client.py").write_text(
        "from library import State\nfrom callback import callback\n"
        "state = State()\nstate.transaction(callback)\nstate.transaction(lambda: 42)\n"
    )
    assert main(["--root", str(tmp_path), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.column, f.rule) for f in report.findings] == [
        ("client.py", 5, 1, "unused.return")
    ]
