"""Read working files or exact index blobs without changing Git or source files."""

import os
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from code_harness.diagnostics import GateError
from code_harness.engine import registry
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.policy.models import Policy
from code_harness.policy.paths import matches
from code_harness.source import Source

_ENVIRONMENT = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)


@dataclass(frozen=True)
class Selection:
    """Choose one exact source view, keeping base validation outside shell parsing."""

    root: Path
    mode: str
    base: str | None = None


def git(root: Path, arguments: tuple[str, ...]) -> bytes:
    """Run read-only Git commands and preserve filenames as NUL-delimited bytes."""
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise GateError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _paths(output: bytes) -> tuple[str, ...]:
    if output and not output.endswith(b"\0"):
        raise GateError("Git returned a malformed filename list")
    return tuple(path.decode("utf-8") for path in output.split(b"\0") if path)


def selected(path: str, policy: Policy, analyzers: AnalyzerRegistry) -> bool:
    """Infrastructure directories are never authored input; all other scope is explicit."""
    return (
        analyzers.language_for(path) is not None
        and not _ENVIRONMENT.intersection(Path(path).parts)
        and matches(path, policy.include)
        and not matches(path, policy.exclude)
    )


def _disk_paths(root: Path, policy: Policy, analyzers: AnalyzerRegistry) -> tuple[str, ...]:
    result: list[str] = []
    for directory, children, filenames in os.walk(root, onerror=_walk_error):
        children[:] = [name for name in children if name not in _ENVIRONMENT]
        for name in children:
            if (Path(directory) / name).is_symlink():
                raise GateError(f"Refusing to traverse symlink directory: {directory}/{name}")
        for filename in filenames:
            path = (Path(directory) / filename).relative_to(root).as_posix()
            if selected(path, policy, analyzers):
                result.append(path)
    return tuple(sorted(result))


def _walk_error(error: OSError) -> None:
    raise GateError(f"Cannot enumerate source files: {error}") from error


def _git_paths(selection: Selection) -> tuple[str, ...]:
    root = selection.root
    actual = Path(git(root, ("rev-parse", "--show-toplevel")).decode().strip()).resolve()
    if root != actual:
        raise GateError("For Git modes, --root must be the repository root")
    if selection.mode == "staged":
        if git(root, ("ls-files", "--unmerged", "-z")):
            raise GateError("Resolve unmerged index entries before checking staged files")
        return _paths(
            git(
                root,
                ("diff", "--cached", "--name-only", "-z", "--no-renames", "--diff-filter=ACMT"),
            )
        )
    if selection.base is None:
        raise GateError("Base mode requires a commit reference")
    revision = (
        git(root, ("rev-parse", "--verify", "--end-of-options", f"{selection.base}^{{commit}}"))
        .decode()
        .strip()
    )
    changed = _paths(
        git(
            root,
            ("diff", "--name-only", "-z", "--no-renames", "--diff-filter=ACMT", revision, "--"),
        )
    )
    untracked = _paths(git(root, ("ls-files", "--others", "--exclude-standard", "-z")))
    return tuple(sorted(set((*changed, *untracked))))


def read_disk(root: Path, path: str) -> bytes:
    """Reject symlink traversal, including a symlink in an ancestor directory."""
    current = root
    for part in Path(path).parts:
        current = current / part
        if current.is_symlink():
            raise GateError(f"Refusing source/config symlink: {path}")
    if not current.resolve().is_relative_to(root):
        raise GateError(f"Path escapes root: {path}")
    return current.read_bytes()


def read_index(root: Path, path: str) -> bytes:
    """Check index mode before reading a blob; staged symlinks are not source."""
    entries = git(root, ("ls-files", "--stage", "-z", "--", path)).split(b"\0")
    exact = [entry for entry in entries if entry and entry.split(b"\t", 1)[1].decode() == path]
    if len(exact) != 1 or exact[0].split(b" ", 1)[0] not in {b"100644", b"100755"}:
        raise GateError(f"Expected one regular staged file: {path}")
    return git(root, ("show", f":{path}"))


def sources(
    selection: Selection, policy: Policy, analyzers: AnalyzerRegistry | None = None
) -> tuple[Source, ...]:
    """Read exact snapshots and attach edit lines for affected-scope reporting."""
    analyzers = analyzers if analyzers is not None else registry()
    paths = (
        _disk_paths(selection.root, policy, analyzers)
        if selection.mode == "all"
        else _git_paths(selection)
    )
    inputs = _read_sources(selection, paths, policy, analyzers)
    return inputs if selection.mode == "all" else _changed_sources(selection, inputs)


def usage_sources(
    selection: Selection, policy: Policy, analyzers: AnalyzerRegistry
) -> tuple[Source, ...]:
    """Read unchanged reference evidence from the same disk or index view as the audit."""
    if selection.mode == "staged":
        paths = _paths(git(selection.root, ("ls-files", "--cached", "-z")))
    else:
        paths = _disk_paths(selection.root, policy, analyzers)
    return _read_sources(selection, paths, policy, analyzers)


def _read_sources(
    selection: Selection, paths: tuple[str, ...], policy: Policy, analyzers: AnalyzerRegistry
) -> tuple[Source, ...]:
    result: list[Source] = []
    for path in paths:
        if not selected(path, policy, analyzers):
            continue
        content = (
            read_index(selection.root, path)
            if selection.mode == "staged"
            else read_disk(selection.root, path)
        )
        content.decode("utf-8")
        language = analyzers.language_for(path)
        if language is None:
            raise GateError(f"Selected source has no registered language: {path}")
        result.append(Source(path, content, language))
    return tuple(result)


def _changed_sources(selection: Selection, inputs: tuple[Source, ...]) -> tuple[Source, ...]:
    """Use zero-context diffs from the same index or working view as source reads."""
    comparison = ("--cached",)
    untracked: frozenset[str] = frozenset()
    if selection.mode != "staged":
        if selection.base is None:
            raise GateError("Base mode requires a commit reference")
        revision = (
            git(
                selection.root,
                ("rev-parse", "--verify", "--end-of-options", f"{selection.base}^{{commit}}"),
            )
            .decode()
            .strip()
        )
        comparison = (revision,)
        untracked = frozenset(
            _paths(git(selection.root, ("ls-files", "--others", "--exclude-standard", "-z")))
        )
    result: list[Source] = []
    for source in inputs:
        if source.path in untracked:
            result.append(source)
            continue
        diff = git(
            selection.root,
            (
                "diff",
                *comparison,
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--unified=0",
                "--",
                f":(literal){source.path}",
            ),
        )
        result.append(replace(source, changed_lines=_changed_lines(diff)))
    return tuple(result)


def _changed_lines(diff: bytes) -> frozenset[int] | None:
    """Keep deletion anchors and conservatively include removed directive targets.

    Removed marker text only expands scope; parser comment evidence from the
    audited snapshot exclusively controls suppression and directive validation.
    """
    touched: set[int] = set()
    target: int | None = None
    for line in diff.splitlines():
        if line.startswith(b"new file mode "):
            return None
        if line.startswith(b"@@"):
            lines = _hunk_range(line)
            touched.update(lines or (max(1, lines.start),))
            target = lines.stop if lines else lines.start + 1
        elif target is not None and line.startswith(b"-") and b"code-harness:" in line:
            touched.add(target)
    return frozenset(touched)


def _hunk_range(line: bytes) -> range:
    match = re.fullmatch(rb"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@.*", line)
    if match is None:
        raise GateError("Git returned a malformed diff hunk")
    start = int(match[1])
    count = int(match[2]) if match[2] is not None else 1
    if count and start < 1:
        raise GateError("Git returned an invalid changed-line range")
    return range(start, start + count)
