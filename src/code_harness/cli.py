"""Read-only command-line gate; 0 means pass, 1 findings, 2 input/tool failure."""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from code_harness.diagnostics import AnalysisError, Finding, GateError, Report
from code_harness.engine import registry
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.policy.models import Policy
from code_harness.semantics.usage import USAGE_RULES
from code_harness.snapshots import Selection, git, read_disk, read_index, sources, usage_sources
from code_harness.source import Source


class _Arguments(argparse.Namespace):
    root: str
    config: str
    all_files: bool
    staged: bool
    base: str | None
    format: str


def _arguments(arguments: list[str] | None) -> _Arguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Source root (repository root for Git modes)")
    parser.add_argument(
        "--config",
        default=".codeharness/code-harness.json",
        help="Policy path relative to root (default: .codeharness/code-harness.json)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--all", dest="all_files", action="store_true", help="Audit all selected files"
    )
    mode.add_argument(
        "--staged",
        action="store_true",
        help="Audit affected definitions/statements in index blobs with index policy",
    )
    mode.add_argument(
        "--base", help="Audit affected definitions/statements plus complete untracked sources"
    )
    options = _Arguments()
    parser.parse_args(arguments, namespace=options)
    return options


def _policy(selection: Selection, path: str) -> Policy:
    if Path(path).is_absolute() or ".." in Path(path).parts:
        raise GateError("Policy must be a path inside --root")
    if selection.mode == "staged":
        policy = read_index(selection.root, path)
        changes = git(selection.root, ("diff", "--cached", "--name-only", "-z", "--", path))
        if changes:
            raise GateError("Policy changed in index; review it and run --all before adoption")
    else:
        policy = read_disk(selection.root, path)
    return Policy.model_validate_json(policy)


def _sort_key(finding: Finding) -> tuple[str, int, int, str, str]:
    return finding.path, finding.line, finding.column, finding.rule, finding.message


def _report(report: Report, output: str) -> None:
    if output == "json":
        print(report.model_dump_json(indent=2))
        return
    for finding in report.findings:
        label = "warning: " if finding.severity == "warning" else ""
        print(
            f"{finding.path}:{finding.line}:{finding.column}: "
            f"{label}{finding.rule}: {finding.message}"
        )
    print(f"Diagnostic scope: {report.scope}.")
    if report.usage_files:
        print(f"Usage reference scope: {report.usage_files} files.")
    if report.disabled_checkers:
        print(f"Disabled checkers: {', '.join(report.disabled_checkers)}")
    print(f"Architecture {report.mode}: {report.files} files; {len(report.findings)} findings.")


def main(arguments: list[str] | None = None, analyzers: AnalyzerRegistry | None = None) -> int:
    """Require an explicit policy and report empty full audits as configuration errors."""
    options = _arguments(arguments)
    mode = "staged" if options.staged else "all" if options.all_files else "base"
    selection = Selection(Path(options.root).resolve(), mode, options.base)
    try:
        analyzers = analyzers if analyzers is not None else registry()
        policy = _policy(selection, options.config)
        inputs = sources(selection, policy, analyzers)
        if not inputs and mode == "all":
            raise GateError("No supported source files selected; check root and policy scope")
        evidence = _usage_evidence(selection, inputs, policy, analyzers)
        findings = tuple(
            sorted(
                analyzers.analyze_sources(inputs, policy, evidence),
                key=_sort_key,
            )
        )
        report = Report(
            mode=mode,
            scope="full_files" if mode == "all" else "affected_definitions_and_statements",
            files=len(inputs),
            usage_files=len(evidence),
            findings=findings,
            disabled_checkers=tuple(sorted(policy.checkers.disabled_checkers())),
        )
    except (AnalysisError, GateError, OSError, UnicodeError, ValidationError, ValueError) as error:
        print(f"Architecture gate error: {error}", file=sys.stderr)
        return 2
    _report(report, options.format)
    return int(any(finding.severity == "error" for finding in report.findings))


def _usage_evidence(
    selection: Selection, inputs: tuple[Source, ...], policy: Policy, analyzers: AnalyzerRegistry
) -> tuple[Source, ...]:
    if not inputs or all(rule in policy.checkers.disabled_rules() for rule in USAGE_RULES):
        return ()
    return inputs if selection.mode == "all" else usage_sources(selection, policy, analyzers)
