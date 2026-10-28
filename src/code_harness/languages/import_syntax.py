"""Tree-sitter interpretation of dependency evidence for built-in grammars."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.architecture.models import Import
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.source import Source


@dataclass(frozen=True)
class TreeImports:
    """Interpret literal Go and JS-family imports without evaluating escapes."""

    def extract(self, context: TreeContext) -> tuple[Import, ...]:
        result: list[Import] = []
        for node in walk(context.root):
            target = self._module_node(node, context.source)
            if target is not None:
                module = self._literal(target, context.source)
                if module is not None:
                    result.append(
                        Import(module, node.start_point.row + 1, node.start_point.column + 1)
                    )
        return tuple(result)

    def _literal(self, node: Node, source: Source) -> str | None:
        if node.type not in {"string", "interpreted_string_literal", "raw_string_literal"}:
            return None
        raw = spelling(node, source)
        return None if "\\" in raw else raw[1:-1]

    def _module_node(self, node: Node, source: Source) -> Node | None:
        if node.type in {"import_statement", "export_statement", "import_require_clause"}:
            return field(node, "source")
        if node.type == "import_spec":
            return field(node, "path")
        if node.type == "call_expression":
            callee, arguments = field(node, "function"), field(node, "arguments")
            if callee is not None and spelling(callee, source) in {"require", "import"}:
                if arguments is not None and len(arguments.named_children) == 1:
                    return arguments.named_children[0]
        return None
