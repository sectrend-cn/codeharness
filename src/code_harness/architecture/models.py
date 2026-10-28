"""Syntactically visible dependency contracts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Import:
    """A visible dependency at its source location."""

    module: str
    line: int
    column: int
