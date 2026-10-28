"""GoLanguage identity, discovery and tree-sitter grammar."""

from dataclasses import dataclass, field

import tree_sitter_go
from tree_sitter import Language as Grammar

from code_harness.parsing.treesitter import TreeParser
from code_harness.source import Language, LanguageDefinition, Source


class GoParser(TreeParser):
    """Supply the terminal newline required by Go's semicolon grammar."""

    def content(self, source: Source) -> bytes:
        content = source.content
        return content if content.endswith(b"\n") else content + b"\n"


@dataclass(frozen=True)
class GoLanguage:
    """Own syntax parsing independently of application rule composition."""

    definition: LanguageDefinition = LanguageDefinition(Language.GO, (".go",))
    parser: TreeParser = field(default_factory=lambda: GoParser(Grammar(tree_sitter_go.language())))
