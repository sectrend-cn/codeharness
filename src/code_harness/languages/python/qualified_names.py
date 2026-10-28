"""Python built-in identity exposed to the shared alias resolver."""

from dataclasses import dataclass

from code_harness.languages.alias_syntax import GrammarNames


@dataclass(frozen=True)
class PythonNameSyntax(GrammarNames):
    """Only recognized unshadowed Python output APIs receive built-in identity."""

    builtins: frozenset[str] = frozenset({"print", "open"})
