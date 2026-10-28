"""Go grouped-parameter and import grammar interpretation."""

from tree_sitter import Node

from code_harness.languages.import_syntax import TreeImports
from code_harness.languages.metric_syntax import GrammarMetrics
from code_harness.source import Source


class GoMetrics(GrammarMetrics):
    """Count all names in grouped Go parameter declarations."""

    def parameter_count(self, node: Node, source: Source) -> int:
        return max(1, len(node.children_by_field_name("name")))


class GoImports(TreeImports):
    """Only Go import specifications declare package dependencies."""

    def _module_node(self, node: Node, source: Source) -> Node | None:
        return node.child_by_field_name("path") if node.type == "import_spec" else None
