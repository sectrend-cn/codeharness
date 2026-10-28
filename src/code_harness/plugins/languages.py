"""Language discovery contracts independent of rule selection."""

from pathlib import PurePosixPath
from typing import Protocol

from code_harness.diagnostics import AnalysisError
from code_harness.parsing.treesitter import TreeParser
from code_harness.source import Language, LanguageDefinition


class LanguagePlugin(Protocol):
    """Own an identity, its suffixes and its tree-sitter parser."""

    @property
    def definition(self) -> LanguageDefinition: ...

    @property
    def parser(self) -> TreeParser: ...


class LanguageRegistry:
    """Own atomic grammar identity and suffix discovery independently of rules."""

    def __init__(self) -> None:
        self._definitions: dict[Language, LanguageDefinition] = {}
        self._suffixes: dict[str, Language] = {}

    def validate(self, definition: LanguageDefinition) -> None:
        """Check discovery ambiguity before publishing registration state."""
        if definition.language in self._definitions:
            raise AnalysisError(f"Duplicate analyzer for language: {definition.language}")
        suffixes = definition.suffixes
        if not suffixes or len(set(suffixes)) != len(suffixes):
            raise AnalysisError(f"Invalid suffix declarations for language: {definition.language}")
        for suffix in suffixes:
            if PurePosixPath("source" + suffix).suffix != suffix or not suffix.startswith("."):
                raise AnalysisError(f"Invalid language suffix: {suffix}")
            if suffix in self._suffixes:
                raise AnalysisError(f"Conflicting language suffix: {suffix}")

    def register(self, definition: LanguageDefinition) -> None:
        """Register a grammar's discovery contract without requiring a rule set."""
        self.validate(definition)
        self._definitions[definition.language] = definition
        self._suffixes.update((suffix, definition.language) for suffix in definition.suffixes)

    def language_for(self, path: str) -> Language | None:
        """Resolve source suffixes through explicit language registrations."""
        return self._suffixes.get(PurePosixPath(path).suffix)
