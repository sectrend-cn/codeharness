"""Syntax recovery warns while independent defects and source snapshots remain intact."""

import subprocess
import sys
from pathlib import Path

import pytest

from code_harness.diagnostics import Report
from code_harness.engine import check
from code_harness.policy.models import Policy
from code_harness.source import Language, Source


@pytest.mark.parametrize(
    ("language", "code", "expected"),
    [
        (Language.GO, "package demo\ntype Payload interface{}\nfunc broken( {", "type.broad"),
        (Language.JAVASCRIPT, "// @ts-ignore\nfunction broken( {", "type.suppression"),
        (Language.TYPESCRIPT, "type Payload = any;\nconst broken: = ;", "type.broad"),
        (Language.TSX, "type Payload = any;\nconst broken = <div>;", "type.broad"),
        (Language.PYTHON, "# type: ignore\ndef broken(:\n", "type.suppression"),
    ],
)
def test_recovered_tree_still_reports_independent_defects(
    language: Language, code: str, expected: str, caplog: pytest.LogCaptureFixture
) -> None:
    findings = check(Source("example", code.encode(), language), Policy())
    assert expected in {finding.rule for finding in findings}
    assert "syntax.invalid" not in {finding.rule for finding in findings}
    assert "analysis results may be inaccurate" in caplog.text
    assert all(record.levelname == "WARNING" for record in caplog.records)


def test_python_type_comments_preserve_metrics_and_architecture(
    caplog: pytest.LogCaptureFixture,
) -> None:
    policy = Policy.model_validate_json(
        '{"checkers":{"function_size":{"parameters":1},'
        '"architecture.owner":{"owners":[{"name":"other","paths":["other/*"]}]},'
        '"architecture.object_model":{"paths":["*"]}}}'
    )
    code = (
        b"def run(first: int, second: int) -> int:\n    return first + second\n"
        b"if language == 'python':\n    run(1, 2)\n"
        b"value: int = 1 # type: int\n"
    )
    findings = check(Source("app.py", code, Language.PYTHON), policy)
    assert {finding.rule for finding in findings} == {
        "size.parameters",
        "architecture.owner",
        "architecture.dispatch",
        "architecture.object_model",
        "unused.return",
    }
    assert not caplog.records


@pytest.mark.parametrize("output", ["text", "json"])
@pytest.mark.parametrize("defect", [False, True])
def test_cli_warns_on_stderr_and_continues_other_files(
    tmp_path: Path, output: str, defect: bool
) -> None:
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    broken = tmp_path / "broken.py"
    broken.write_text("def broken(:\n")
    content = "type Payload = any;" if defect else "const value: number = 1;"
    (tmp_path / "other.ts").write_text(content)
    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "code_harness",
            "--root",
            str(tmp_path),
            "--all",
            "--format",
            output,
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == int(defect)
    assert "syntax warning" in result.stderr
    assert "analysis results may be inaccurate" in result.stderr
    assert "syntax.invalid" not in result.stdout
    assert ("type.broad" in result.stdout) == defect
    if output == "json":
        report = Report.model_validate_json(result.stdout)
        assert report.files == 2
        assert len(report.findings) == int(defect)
    assert broken.read_text() == "def broken(:\n"
