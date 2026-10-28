"""JavaScriptLanguage identity, discovery and tree-sitter grammar."""

from dataclasses import dataclass, field

import tree_sitter_javascript
from tree_sitter import Language as Grammar

from code_harness.parsing.treesitter import TreeParser
from code_harness.source import Language, LanguageDefinition


@dataclass(frozen=True)
class JavaScriptLanguage:
    """Own syntax parsing independently of application rule composition."""

    definition: LanguageDefinition = LanguageDefinition(
        Language.JAVASCRIPT, (".js", ".jsx", ".mjs", ".cjs")
    )
    parser: TreeParser = field(
        default_factory=lambda: TreeParser(Grammar(tree_sitter_javascript.language()))
    )
