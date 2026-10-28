"""Java identity, discovery and tree-sitter grammar."""

from dataclasses import dataclass, field

import tree_sitter_java
from tree_sitter import Language as Grammar

from code_harness.parsing.treesitter import TreeParser
from code_harness.source import Language, LanguageDefinition


@dataclass(frozen=True)
class JavaLanguage:
    """Own Java parsing independently of application rule composition."""

    definition: LanguageDefinition = LanguageDefinition(Language.JAVA, (".java",))
    parser: TreeParser = field(
        default_factory=lambda: TreeParser(Grammar(tree_sitter_java.language()))
    )
