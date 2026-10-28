"""TypeScriptLanguage identity, discovery and tree-sitter grammar."""

from dataclasses import dataclass, field

import tree_sitter_typescript
from tree_sitter import Language as Grammar

from code_harness.parsing.treesitter import TreeParser
from code_harness.source import Language, LanguageDefinition


@dataclass(frozen=True)
class TypeScriptLanguage:
    """Own syntax parsing independently of application rule composition."""

    definition: LanguageDefinition = LanguageDefinition(
        Language.TYPESCRIPT, (".ts", ".mts", ".cts")
    )
    parser: TreeParser = field(
        default_factory=lambda: TreeParser(Grammar(tree_sitter_typescript.language_typescript()))
    )


@dataclass(frozen=True)
class TsxLanguage:
    """Register JSX-capable TypeScript as a distinct grammar."""

    definition: LanguageDefinition = LanguageDefinition(Language.TSX, (".tsx",))
    parser: TreeParser = field(
        default_factory=lambda: TreeParser(Grammar(tree_sitter_typescript.language_tsx()))
    )
