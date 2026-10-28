"""TypeScript import-equals declarations extend JavaScript module syntax."""

from tree_sitter import Node

from code_harness.languages.javascript.syntax import JavaScriptImports
from code_harness.source import Source


class TypeScriptImports(JavaScriptImports):
    """Recognize TypeScript import-require clauses alongside ES modules."""

    def _module_node(self, node: Node, source: Source) -> Node | None:
        if node.type == "import_require_clause":
            return node.child_by_field_name("source")
        return super()._module_node(node, source)
