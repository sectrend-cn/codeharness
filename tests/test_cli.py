"""Verify fail-closed CLI behavior and exact Git snapshot selection in isolated repos."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.models import Report


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments), check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "gate@example.invalid")
    _git(tmp_path, "config", "user.name", "Gate Test")
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text("{}\n")
    (tmp_path / "app.py").write_text("def run() -> int:\n    return 1\n")
    _git(tmp_path, "add", ".codeharness/code-harness.json", "app.py")
    _git(tmp_path, "commit", "-qm", "fixture")
    return tmp_path


def test_full_json_report_has_declared_scope(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--root", str(repository), "--all", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.files == 1
    assert report.mode == "all"
    assert report.findings == ()


def test_staged_reads_index_instead_of_working_copy(repository: Path) -> None:
    (repository / "app.py").write_text("def run(value):\n    return value\n")
    _git(repository, "add", "app.py")
    (repository / "app.py").write_text("def run(value: int) -> int:\n    return value\n")
    working_copy = (repository / "app.py").read_bytes()
    before = _git(repository, "status", "--porcelain=v1")
    assert main(["--root", str(repository), "--staged"]) == 1
    assert (repository / "app.py").read_bytes() == working_copy
    assert _git(repository, "status", "--porcelain=v1") == before


def test_staged_ignores_unstaged_invalid_source(repository: Path) -> None:
    (repository / "app.py").write_text("def run() -> int:\n    return 2\n")
    _git(repository, "add", "app.py")
    (repository / "app.py").write_text("def broken(:")
    assert main(["--root", str(repository), "--staged"]) == 0


def test_base_includes_complete_untracked_sources(repository: Path) -> None:
    (repository / "new name\nfile.ts").write_text("type Payload = any;")
    assert main(["--root", str(repository), "--base", "HEAD"]) == 1


def test_deleted_sources_do_not_fail_or_get_read(repository: Path) -> None:
    (repository / "app.py").unlink()
    assert main(["--root", str(repository), "--base", "HEAD"]) == 0


def test_staged_policy_changes_require_full_review(repository: Path) -> None:
    (repository / ".codeharness/code-harness.json").write_text('{"include": []}')
    _git(repository, "add", ".codeharness/code-harness.json")
    assert main(["--root", str(repository), "--staged"]) == 2


def test_unstaged_policy_cannot_weaken_staged_gate(repository: Path) -> None:
    (repository / "app.py").write_text("def run(value):\n    return value")
    _git(repository, "add", "app.py")
    (repository / ".codeharness/code-harness.json").write_text('{"include": []}')
    assert main(["--root", str(repository), "--staged"]) == 1


@pytest.mark.parametrize(
    "policy",
    [
        '{"unknown_setting": true}',
        '{"checkers": {"function_size": {"lines": 0}}}',
        '{"checkers": {"function_size": {"lines": "50"}}}',
        '{"version": 3}',
        "{",
    ],
)
def test_malformed_or_unsupported_policy_is_an_error(repository: Path, policy: str) -> None:
    (repository / ".codeharness/code-harness.json").write_text(policy)
    assert main(["--root", str(repository), "--all"]) == 2


def test_unknown_base_and_missing_policy_are_errors(repository: Path) -> None:
    assert main(["--root", str(repository), "--base", "does-not-exist"]) == 2
    assert main(["--root", str(repository), "--all", "--config", "absent.json"]) == 2


def test_empty_audit_and_outside_config_are_errors(repository: Path) -> None:
    (repository / ".codeharness/code-harness.json").write_text('{"include": []}')
    assert main(["--root", str(repository), "--all"]) == 2
    assert main(["--root", str(repository), "--all", "--config", "../policy.json"]) == 2


def test_symlink_sources_are_rejected(repository: Path) -> None:
    (repository / "link.py").symlink_to(repository / "app.py")
    assert main(["--root", str(repository), "--all"]) == 2
    _git(repository, "add", "link.py")
    assert main(["--root", str(repository), "--staged"]) == 2


def test_invalid_utf8_is_an_error(repository: Path) -> None:
    (repository / "app.py").write_bytes(b"\xff")
    assert main(["--root", str(repository), "--all"]) == 2


def test_public_cli_reports_type_violation(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "payload.ts").write_text("type Payload = any;\n")

    assert main(["--root", str(repository), "--all"]) == 1
    assert "type.broad" in capsys.readouterr().out


def test_public_cli_reports_metric_violation(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    branches = " ".join(f"if (value === {index}) {{}}" for index in range(10))
    (repository / "branches.js").write_text(f"function run(value) {{ {branches} }}\n")

    assert main(["--root", str(repository), "--all"]) == 1
    assert "size.complexity" in capsys.readouterr().out


def test_public_cli_reports_architecture_violation(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"architecture.import":{"boundaries":[{"name":"domain",'
        '"sources":["src/domain/*"],"forbidden_imports":["blocked/*"]}]}}}\n'
    )
    source = repository / "src" / "domain" / "feature.ts"
    source.parent.mkdir(parents=True)
    source.write_text('import { Item } from "blocked/package";\n')

    assert main(["--root", str(repository), "--all"]) == 1
    assert "architecture.import" in capsys.readouterr().out


def test_unstaged_disable_does_not_change_staged_enforcement(repository: Path) -> None:
    (repository / "app.py").write_text("def run(value):\n    return value")
    _git(repository, "add", "app.py")
    (repository / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"type.signature":{"enabled":false}}}'
    )
    assert main(["--root", str(repository), "--all"]) == 0
    assert main(["--root", str(repository), "--staged"]) == 1
    _git(repository, "add", ".codeharness/code-harness.json")
    assert main(["--root", str(repository), "--staged"]) == 2


def test_default_policy_does_not_fall_back_to_root(tmp_path: Path) -> None:
    (tmp_path / "code-harness.json").write_text('{"version": 2}')
    (tmp_path / "app.py").write_text("value: int = 1\n")
    assert main(["--root", str(tmp_path), "--all"]) == 2
    assert main(["--root", str(tmp_path), "--all", "--config", "code-harness.json"]) == 0


def test_explicit_policy_overrides_default(repository: Path) -> None:
    (repository / "code-harness.json").write_text('{"include": []}')
    assert main(["--root", str(repository), "--all"]) == 0
    assert main(["--root", str(repository), "--all", "--config", "code-harness.json"]) == 2


def test_example_policy_enforces_root_relative_boundaries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    example = Path(__file__).parents[1] / "examples/.codeharness/code-harness.json"
    (tmp_path / ".codeharness").mkdir()
    (tmp_path / ".codeharness/code-harness.json").write_bytes(example.read_bytes())
    source = tmp_path / "src/domain/feature.ts"
    source.parent.mkdir(parents=True)
    source.write_text("export const value: number = 1;\n")
    assert main(["--root", str(tmp_path), "--all"]) == 0
    capsys.readouterr()
    source.write_text('import { value } from "../adapters/storage";\n')
    assert main(["--root", str(tmp_path), "--all"]) == 1
    output = capsys.readouterr().out
    assert "architecture.import" in output
    assert "architecture.owner" not in output


def test_staged_usage_reads_unchanged_consumers_from_index(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / "models.py").write_text("class Item:\n    value: int = 1\n")
    (repository / "consumer.py").write_text(
        "from models import Item\ndef read(item: Item) -> int:\n    return item.value\n"
    )
    _git(repository, "add", "models.py", "consumer.py")
    _git(repository, "commit", "-qm", "usage fixture")
    (repository / "models.py").write_text("class Item:\n    value: int = 2\n")
    _git(repository, "add", "models.py")
    (repository / "consumer.py").write_text("def broken(:")
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.files == 1
    assert report.usage_files == 3
    assert report.findings == ()


def test_staged_structure_uses_index_paths_despite_working_tree_move(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repository / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"architecture.structure":{"placements":['
        '{"name":"language rules","paths":["*_rules.py"],'
        '"allowed_paths":["languages/*"]}]}}}'
    )
    assert _git(repository, "add", ".codeharness/code-harness.json") == ""
    assert _git(repository, "commit", "-qm", "configure structure") == ""
    source = repository / "python_rules.py"
    source.write_text("value: int = 1\n")
    assert _git(repository, "add", "python_rules.py") == ""
    (repository / "languages").mkdir()
    moved = repository / "languages/python_rules.py"
    source.rename(moved)
    before = _git(repository, "status", "--porcelain=v1")
    assert main(["--root", str(repository), "--staged"]) == 1
    assert "architecture.structure" in capsys.readouterr().out
    assert main(["--root", str(repository), "--base", "HEAD"]) == 0
    assert _git(repository, "status", "--porcelain=v1") == before
    assert moved.read_text() == "value: int = 1\n"


@pytest.mark.parametrize("mode", ["--base", "--staged"])
@pytest.mark.parametrize(
    "case",
    [
        (
            "def old(value):\n    return value\n\ndef changed(value):\n    return 1\n",
            "def old(value):\n    return value\n\ndef changed(value):\n    return 2\n",
            {4},
        ),
        (
            "@decorate(1)\ndef changed(value):\n    return value\n\ndef old(value):\n"
            "    return value\n",
            "@decorate(2)\ndef changed(value):\n    return value\n\ndef old(value):\n"
            "    return value\n",
            {2},
        ),
        (
            "class Model:\n    def changed(self, value):\n        return 1\n"
            "    def old(self, value):\n        return value\n",
            "class Model:\n    def changed(self, value):\n        return 2\n"
            "    def old(self, value):\n        return value\n",
            {2},
        ),
        (
            "@decorate(1)\nclass Model:\n    def first(self, value):\n"
            "        return value\n    def second(self, value):\n        return value\n",
            "@decorate(2)\nclass Model:\n    def first(self, value):\n"
            "        return value\n    def second(self, value):\n        return value\n",
            {3, 5},
        ),
        (
            "def changed(value):\n    unused = 1\n    return value\n\n"
            "def old(value):\n    return value\n",
            "def changed(value):\n    return value\n\ndef old(value):\n    return value\n",
            {1},
        ),
        (
            "def outer(value):\n    def inner(other):\n        return 1\n"
            "    return inner(value)\n\ndef old(value):\n    return value\n",
            "def outer(value):\n    def inner(other):\n        return 2\n"
            "    return inner(value)\n\ndef old(value):\n    return value\n",
            {1, 2},
        ),
    ],
)
def test_changed_modes_report_affected_definitions(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    case: tuple[str, str, set[int]],
) -> None:
    before, after, expected_lines = case
    source = repository / "app.py"
    source.write_text(before)
    _git(repository, "add", "app.py")
    _git(repository, "commit", "-qm", "scope fixture")
    source.write_text(after)
    options = ["HEAD"] if mode == "--base" else []
    if mode == "--staged":
        _git(repository, "add", "app.py")
    assert main(["--root", str(repository), mode, *options, "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.scope == "affected_definitions_and_statements"
    assert {f.line for f in report.findings if f.rule == "type.signature"} == expected_lines


def test_changed_module_statement_expands_multiline_expression(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = repository / "app.py"
    source.write_text(
        "import json\nbody = json.dumps({\n    'count': 1,\n})\ndef old(value):\n    return value\n"
    )
    _git(repository, "add", "app.py")
    _git(repository, "commit", "-qm", "statement fixture")
    source.write_text(source.read_text().replace("'count': 1", "'count': 2"))
    assert main(["--root", str(repository), "--base", "HEAD", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.rule, f.line) for f in report.findings] == [("type.broad", 2)]


def test_unchanged_debt_is_visible_only_in_full_audit(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = repository / "app.py"
    source.write_text("def old(value):\n    return value\n\nvalue: int = 1\n")
    _git(repository, "add", "app.py")
    _git(repository, "commit", "-qm", "debt fixture")
    source.write_text(source.read_text().replace("value: int = 1", "value: int = 2"))
    assert main(["--root", str(repository), "--base", "HEAD", "--format", "json"]) == 0
    changed = Report.model_validate_json(capsys.readouterr().out)
    assert changed.findings == ()
    assert main(["--root", str(repository), "--all", "--format", "json"]) == 1
    full = Report.model_validate_json(capsys.readouterr().out)
    assert full.scope == "full_files"
    assert any(f.rule == "type.signature" for f in full.findings)


@pytest.mark.parametrize(
    "case",
    [
        (
            "sample.go",
            "package sample\nfunc Old(value any) {}\nfunc Changed(value any) { println(1) }\n",
            "package sample\nfunc Old(value any) {}\nfunc Changed(value any) { println(2) }\n",
            "type.broad",
        ),
        (
            "sample.ts",
            "function old(value: any) { return value; }\n"
            "function changed(value: any) { return 1; }\n",
            "function old(value: any) { return value; }\n"
            "function changed(value: any) { return 2; }\n",
            "type.broad",
        ),
        (
            "Sample.java",
            "class Sample {\n Object old(Object value) { return value; }\n"
            " Object changed(Object value) { return null; }\n}\n",
            "class Sample {\n Object old(Object value) { return value; }\n"
            " Object changed(Object value) { return value; }\n}\n",
            "type.broad",
        ),
    ],
)
def test_changed_scopes_use_registered_language_grammar(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    case: tuple[str, str, str, str],
) -> None:
    filename, before, after, rule = case
    source = repository / filename
    source.write_text(before)
    _git(repository, "add", filename)
    _git(repository, "commit", "-qm", "language fixture")
    source.write_text(after)
    assert main(["--root", str(repository), "--base", "HEAD", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    findings = [f for f in report.findings if f.rule == rule]
    assert findings
    changed_line = next(
        index for index, line in enumerate(after.splitlines(), 1) if "hanged(" in line
    )
    assert {f.line for f in findings} == {changed_line}


def test_global_exclusion_keeps_other_files_in_the_audit(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (repository / "deferred").mkdir()
    (repository / "deferred/bad.py").write_text("value: object = None\n")
    (repository / "app.py").write_text("value: object = None\n")
    (repository / ".codeharness/code-harness.json").write_text('{"exclude":["deferred/*"]}')
    assert main(["--root", str(repository), "--all", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert report.files == 1
    assert {f.path for f in report.findings} == {"app.py"}


def test_checker_path_exclusions_are_not_silently_accepted(repository: Path) -> None:
    (repository / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"type.broad":{"exclude":["deferred/*"]}}}'
    )
    assert main(["--root", str(repository), "--all"]) == 2


def test_changed_file_obligations_are_not_filtered_by_finding_line(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy = repository / ".codeharness/code-harness.json"
    policy.write_text(
        '{"checkers":{"architecture.owner":{"owners":[{"name":"other","paths":["other/*"]}]},'
        '"architecture.structure":{"placements":[{"name":"app","paths":["app.py"],'
        '"allowed_paths":["src/*"]}]}}}'
    )
    _git(repository, "add", ".codeharness/code-harness.json")
    _git(repository, "commit", "-qm", "file policy fixture")
    (repository / "app.py").write_text("def run() -> int:\n    return 2\n")
    assert main(["--root", str(repository), "--base", "HEAD", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert {f.rule for f in report.findings} == {"architecture.owner", "architecture.structure"}
    assert all(f.scope == "file" for f in report.findings)


def test_staged_encoding_configuration_uses_index_policy(repository: Path) -> None:
    (repository / "app.py").write_text("import codec\nvalue = codec.encode({})\n")
    _git(repository, "add", "app.py")
    (repository / ".codeharness/code-harness.json").write_text(
        '{"checkers":{"type.broad":{"encoding":{"encoders":["codec.encode"]}}}}'
    )
    assert main(["--root", str(repository), "--all"]) == 1
    assert main(["--root", str(repository), "--staged"]) == 0
    _git(repository, "add", ".codeharness/code-harness.json")
    assert main(["--root", str(repository), "--staged"]) == 2


@pytest.mark.parametrize("mode", ["--base", "--staged"])
@pytest.mark.parametrize("operation", ["add", "remove", "replace"])
def test_changed_suppression_selects_following_target(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    operation: str,
) -> None:
    directive = "// code-harness: ignore-next-line type.broad -- Serialized fixture.\n"
    prefix = "export const unrelated = 1;\n"
    target = "const input = JSON.stringify(payload) as Payload;\n"
    source = repository / "test.ts"
    source.write_text(prefix + ("" if operation == "add" else directive) + target)
    assert _git(repository, "add", "test.ts") == ""
    assert _git(repository, "commit", "-qm", "suppression fixture") == ""
    replacement = {"add": directive, "remove": "", "replace": "// ordinary explanation\n"}
    source.write_text(prefix + replacement[operation] + target)
    options = ["HEAD"] if mode == "--base" else []
    if mode == "--staged":
        assert _git(repository, "add", "test.ts") == ""
    assert main(["--root", str(repository), mode, *options, "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    expected = {"type.assertion"} if operation == "add" else {"type.assertion", "type.broad"}
    assert {f.rule for f in report.findings} == expected
    assert {f.line for f in report.findings} == {2 if operation == "remove" else 3}


def test_unstaged_directive_cannot_suppress_index_finding(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = repository / "test.ts"
    target = "const input = JSON.stringify(payload);\n"
    source.write_text(target)
    assert _git(repository, "add", "test.ts") == ""
    source.write_text("// code-harness: ignore-next-line type.broad -- Fixture.\n" + target)
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.path, f.line, f.rule) for f in report.findings] == [("test.ts", 1, "type.broad")]


def test_staged_directive_is_independent_of_disk_removal(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = repository / "test.ts"
    target = "const input = JSON.stringify(payload);\n"
    source.write_text("// code-harness: ignore-next-line type.broad -- Fixture.\n" + target)
    assert _git(repository, "add", "test.ts") == ""
    source.write_text(target)
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 0
    assert Report.model_validate_json(capsys.readouterr().out).findings == ()


@dataclass(frozen=True)
class _SuppressionSource:
    """Bind one repository file to a language's directive marker and target."""

    filename: str
    prefix: str
    directive: str
    target: str

    def body(self, middle: str) -> str:
        return self.prefix + middle + self.target


_PYTHON_SUPPRESSION = _SuppressionSource(
    "test.py",
    "from typing import Any\n",
    "# code-harness: ignore-next-line type.annotation -- Serialized fixture.\n",
    "x: Any = 1\n",
)
_GO_SUPPRESSION = _SuppressionSource(
    "test.go",
    "package sample\n",
    "// code-harness: ignore-next-line type.broad -- Serialized fixture.\n",
    "type Input any\n",
)
_JAVA_SUPPRESSION = _SuppressionSource(
    "Sample.java",
    "class Sample {\n",
    "// code-harness: ignore-next-line type.broad -- Serialized fixture.\n",
    "void run(Object value) { consume(value); }\n}\n",
)


def _write_suppression_source(repository: Path, fixture: _SuppressionSource, middle: str) -> None:
    (repository / fixture.filename).write_text(fixture.body(middle))


@pytest.mark.parametrize("mode", ["--base", "--staged"])
@pytest.mark.parametrize("operation", ["add", "remove", "replace"])
def test_python_changed_suppression_matrix(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    operation: str,
) -> None:
    fixture = _PYTHON_SUPPRESSION
    _write_suppression_source(repository, fixture, "" if operation == "add" else fixture.directive)
    assert _git(repository, "add", fixture.filename) == ""
    assert _git(repository, "commit", "-qm", "python suppression fixture") == ""
    replacement = {"add": fixture.directive, "remove": "", "replace": "# explanation\n"}
    _write_suppression_source(repository, fixture, replacement[operation])
    options = ["HEAD"] if mode == "--base" else []
    if mode == "--staged":
        assert _git(repository, "add", fixture.filename) == ""
    assert main(["--root", str(repository), mode, *options, "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    expected = {"type.broad"} if operation == "add" else {"type.annotation", "type.broad"}
    assert {f.rule for f in report.findings} == expected
    assert {f.line for f in report.findings} == {2 if operation == "remove" else 3}


@pytest.mark.parametrize(("mode", "operation"), [("--base", "add"), ("--staged", "remove")])
def test_go_changed_suppression_samples(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    operation: str,
) -> None:
    fixture = _GO_SUPPRESSION
    _write_suppression_source(repository, fixture, "" if operation == "add" else fixture.directive)
    assert _git(repository, "add", fixture.filename) == ""
    assert _git(repository, "commit", "-qm", "go suppression fixture") == ""
    _write_suppression_source(repository, fixture, fixture.directive if operation == "add" else "")
    options = ["HEAD"] if mode == "--base" else []
    if mode == "--staged":
        assert _git(repository, "add", fixture.filename) == ""
    exit_code = main(["--root", str(repository), mode, *options, "--format", "json"])
    report = Report.model_validate_json(capsys.readouterr().out)
    expected = [] if operation == "add" else [(fixture.filename, 2, "type.broad")]
    assert exit_code == (0 if operation == "add" else 1)
    assert [(f.path, f.line, f.rule) for f in report.findings] == expected


@pytest.mark.parametrize(("mode", "operation"), [("--base", "replace"), ("--staged", "add")])
def test_java_changed_suppression_samples(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    operation: str,
) -> None:
    fixture = _JAVA_SUPPRESSION
    _write_suppression_source(repository, fixture, "" if operation == "add" else fixture.directive)
    assert _git(repository, "add", fixture.filename) == ""
    assert _git(repository, "commit", "-qm", "java suppression fixture") == ""
    replacement = fixture.directive if operation == "add" else "// explanation\n"
    _write_suppression_source(repository, fixture, replacement)
    options = ["HEAD"] if mode == "--base" else []
    if mode == "--staged":
        assert _git(repository, "add", fixture.filename) == ""
    exit_code = main(["--root", str(repository), mode, *options, "--format", "json"])
    report = Report.model_validate_json(capsys.readouterr().out)
    expected = [] if operation == "add" else [(fixture.filename, 3, "type.broad")]
    assert exit_code == (0 if operation == "add" else 1)
    assert [(f.path, f.line, f.rule) for f in report.findings] == expected


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (_PYTHON_SUPPRESSION, [("type.annotation", 2), ("type.broad", 2)]),
        (_GO_SUPPRESSION, [("type.broad", 2)]),
    ],
    ids=["python", "go"],
)
def test_unstaged_directive_cannot_suppress_index_finding_in_any_language(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    fixture: _SuppressionSource,
    expected: list[tuple[str, int]],
) -> None:
    _write_suppression_source(repository, fixture, "")
    assert _git(repository, "add", fixture.filename) == ""
    _write_suppression_source(repository, fixture, fixture.directive)
    assert main(["--root", str(repository), "--staged", "--format", "json"]) == 1
    report = Report.model_validate_json(capsys.readouterr().out)
    assert [(f.rule, f.line) for f in report.findings] == expected


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [(_PYTHON_SUPPRESSION, [("type.broad", 3)]), (_JAVA_SUPPRESSION, [])],
    ids=["python", "java"],
)
def test_staged_directive_is_independent_of_disk_removal_in_any_language(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    fixture: _SuppressionSource,
    expected: list[tuple[str, int]],
) -> None:
    _write_suppression_source(repository, fixture, fixture.directive)
    assert _git(repository, "add", fixture.filename) == ""
    _write_suppression_source(repository, fixture, "")
    exit_code = main(["--root", str(repository), "--staged", "--format", "json"])
    report = Report.model_validate_json(capsys.readouterr().out)
    assert exit_code == (1 if expected else 0)
    assert [(f.rule, f.line) for f in report.findings] == expected


def test_directive_marker_in_diff_filename_does_not_expand_scope(
    repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    filename = "code-harness:example.ts"
    source = repository / filename
    source.write_text("type Old = any;\nexport const changed = 1;\n")
    assert _git(repository, "add", filename) == ""
    assert _git(repository, "commit", "-qm", "filename fixture") == ""
    source.write_text("type Old = any;\nexport const changed = 2;\n")
    assert main(["--root", str(repository), "--base", "HEAD", "--format", "json"]) == 0
    assert Report.model_validate_json(capsys.readouterr().out).findings == ()
