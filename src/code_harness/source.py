"""Language identities and immutable source snapshots."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Language:
    """Open language identity; plugins declare new values without editing an enum."""

    value: str
    PYTHON: ClassVar["Language"]
    GO: ClassVar["Language"]
    JAVA: ClassVar["Language"]
    JAVASCRIPT: ClassVar["Language"]
    TYPESCRIPT: ClassVar["Language"]
    TSX: ClassVar["Language"]

    def __post_init__(self) -> None:
        if not self.value or not self.value.isidentifier():
            raise ValueError("Language identities must be nonempty identifiers")

    def __str__(self) -> str:
        return self.value


Language.PYTHON = Language("python")
Language.GO = Language("go")
Language.JAVA = Language("java")
Language.JAVASCRIPT = Language("javascript")
Language.TYPESCRIPT = Language("typescript")
Language.TSX = Language("tsx")


@dataclass(frozen=True)
class LanguageDefinition:
    """A language plugin owns identity and file discovery."""

    language: Language
    suffixes: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    """An exact UTF-8 source snapshot, independent of its storage location."""

    path: str
    content: bytes
    language: Language
    changed_lines: frozenset[int] | None = None
