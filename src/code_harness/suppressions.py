"""Shared diagnostic suppression and prohibition of unsupported directives."""

import re
from dataclasses import dataclass
from typing import Protocol

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import spelling
from code_harness.policy.type_options import SUPPRESSION

_SUPPRESSION = re.compile(
    r"(?<!\w)(?:type:\s*ignore|noqa|pyright:\s*ignore|mypy:\s*ignore|"
    r"@ts-ignore|@ts-nocheck|@ts-expect-error|eslint-disable(?:-next-line|-line)?|"
    r"nolint|lint:ignore)\b"
)

_DIRECTIVE = re.compile(r"code-harness:\s+ignore-next-line\s+(\S+)\s+--\s+(\S[^\r\n]*)")


class DirectiveSyntax(Protocol):
    """Expose candidate comment nodes and standalone line-comment contents."""

    def candidates(self, context: TreeContext) -> tuple[Node, ...]: ...
    def directive_text(self, node: Node, context: TreeContext) -> str | None: ...


@dataclass(frozen=True)
class LineSuppression:
    """Retain the exact diagnostic selector and its human approval record."""

    path: str
    line: int
    column: int
    rule: str
    reason: str

    @property
    def target_line(self) -> int:
        return self.line + 1

    def matches(self, finding: Finding) -> bool:
        return (finding.path, finding.line, finding.rule) == (
            self.path,
            self.target_line,
            self.rule,
        )

    def unused(self) -> Finding:
        return Finding(
            path=self.path,
            line=self.line,
            column=self.column,
            rule=SUPPRESSION.name,
            message=f"Unused code-harness directive: no {self.rule} finding on the next line "
            f"for reason {self.reason!r}",
        )


@dataclass(frozen=True)
class ParsedSuppressions:
    """Filter exact diagnostics and validate usage within the selected audit scope."""

    directives: tuple[LineSuppression, ...] = ()
    errors: tuple[Finding, ...] = ()

    def target_lines(self, touched: frozenset[int]) -> frozenset[int]:
        return frozenset(
            directive.target_line for directive in self.directives if directive.line in touched
        ) | frozenset(error.line + 1 for error in self.errors if error.line in touched)

    def apply(
        self, findings: tuple[Finding, ...], lines: frozenset[int] | None
    ) -> tuple[Finding, ...]:
        active = tuple(
            directive
            for directive in self.directives
            if lines is None or directive.target_line in lines
        )
        unused = tuple(
            directive.unused()
            for directive in active
            if not any(directive.matches(finding) for finding in findings)
        )
        remaining = tuple(
            finding
            for finding in findings
            if not any(directive.matches(finding) for directive in active)
        )
        return remaining + self._selected_errors(lines) + unused

    def _selected_errors(self, lines: frozenset[int] | None) -> tuple[Finding, ...]:
        return tuple(
            error
            for error in self.errors
            if lines is None or error.line in lines or error.line + 1 in lines
        )


@dataclass(frozen=True)
class CommentSuppressions:
    """Validate parser-owned directives against composed diagnostic identities."""

    syntax: DirectiveSyntax
    rule_ids: tuple[str, ...]

    def parse(self, context: TreeContext) -> ParsedSuppressions:
        directives: list[LineSuppression] = []
        errors: list[Finding] = []
        for node in self.syntax.candidates(context):
            text = self.syntax.directive_text(node, context)
            match = _DIRECTIVE.fullmatch(text) if text is not None else None
            if match is None or match[1] not in self.rule_ids or match[1] == SUPPRESSION.name:
                errors.append(self._invalid(node, context))
            else:
                directives.append(
                    LineSuppression(
                        context.source.path,
                        node.start_point.row + 1,
                        node.start_point.column + 1,
                        match[1],
                        match[2].strip(),
                    )
                )
        return ParsedSuppressions(tuple(directives), tuple(errors))

    def _invalid(self, node: Node, context: TreeContext) -> Finding:
        return Finding(
            path=context.source.path,
            line=node.start_point.row + 1,
            column=node.start_point.column + 1,
            rule=SUPPRESSION.name,
            message="Invalid code-harness directive: require a standalone ignore-next-line "
            "comment, one registered rule other than type.suppression, and -- reason",
        )


class SuppressionSyntax(Protocol):
    """Supply comment tokens and exceptional type-check-disabling syntax."""

    @property
    def requirements(self) -> RuleRequirements: ...

    def comments(self, root: Node) -> tuple[Node, ...]: ...
    def disabled_types(self, context: TreeContext) -> tuple[Node, ...]: ...


@dataclass(frozen=True)
class SuppressionRule:
    """Own comment suppression detection across tree-backed languages."""

    syntax: SuppressionSyntax
    name: str = "builtin.suppressions"
    api_version: int = 2
    rule_ids: tuple[str, ...] = (SUPPRESSION.name,)
    directives: DirectiveSyntax | None = None

    @property
    def requirements(self) -> RuleRequirements:
        return self.syntax.requirements

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        candidates = self.directives.candidates(context) if self.directives is not None else ()
        comments = tuple(
            Finding(
                path=context.source.path,
                line=node.start_point.row + 1,
                column=node.start_point.column + 1,
                rule=SUPPRESSION.name,
                message="Fix the contract; do not suppress a checker diagnostic",
            )
            for node in self.syntax.comments(context.root)
            if node not in candidates and _SUPPRESSION.search(spelling(node, context.source))
        )
        return comments + tuple(
            Finding(
                path=context.source.path,
                line=node.start_point.row + 1,
                column=node.start_point.column + 1,
                rule=SUPPRESSION.name,
                message="Do not disable type checking",
            )
            for node in self.syntax.disabled_types(context)
            if not self.requirements.semantic_evidence
            or not context.require_boundary().contains(node)
        )
