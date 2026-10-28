"""Canonical finding and report contracts."""

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ParseWarning(BaseModel):
    """Parser evidence reported separately from defects and checker configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    line: int
    column: int
    message: str

    def emit(self) -> None:
        """Warn on stderr by default without changing the gate's defect status."""
        logging.getLogger(__name__).warning(
            "%r:%d:%d: syntax warning: %r; analysis results may be inaccurate",
            self.path,
            self.line,
            self.column,
            self.message,
        )


class Finding(BaseModel):
    """One stable, one-based diagnostic suitable for terminal or JSON output."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: str
    line: int
    column: int
    rule: str
    message: str
    severity: Literal["error", "warning"] = "error"
    scope: Literal["line", "file"] = "line"


class Report(BaseModel):
    """Explicit audit scope and results."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: str
    scope: Literal["full_files", "affected_definitions_and_statements"] = "full_files"
    files: int
    usage_files: int = 0
    findings: tuple[Finding, ...]
    disabled_checkers: tuple[str, ...] = ()


class GateError(Exception):
    """An input or infrastructure failure that must not be reported as a pass."""


class AnalysisError(Exception):
    """A required analyzer or registered rule bundle failed."""


class SyntaxFailure(AnalysisError):
    """A parser without a recoverable context warns and skips dependent rules."""

    def __init__(self, warnings: tuple[ParseWarning, ...]) -> None:
        if not warnings:
            raise ValueError("Syntax rejection requires evidence")
        self.warnings = warnings
        super().__init__(warnings[0].message)
