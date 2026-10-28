"""JavaScript function and module grammar interpretation."""

import posixpath

from tree_sitter import Node

from code_harness.architecture.imports import ImportResolver
from code_harness.architecture.models import Import
from code_harness.languages.import_syntax import TreeImports
from code_harness.languages.metric_syntax import GrammarMetrics
from code_harness.parsing.treesitter import field, spelling
from code_harness.source import Source


class JavaScriptMetrics(GrammarMetrics):
    """Identify JS-family executable functions using their shared grammar nodes."""

    def is_function(self, node: Node) -> bool:
        return node.type in {
            "function_declaration",
            "function_expression",
            "generator_function_declaration",
            "generator_function",
            "arrow_function",
            "method_definition",
        }


class JavaScriptImports(TreeImports):
    """Interpret ES modules and literal require/import call dependencies."""

    def _module_node(self, node: Node, source: Source) -> Node | None:
        if node.type in {"import_statement", "export_statement"}:
            return field(node, "source")
        if node.type != "call_expression":
            return None
        callee, arguments = field(node, "function"), field(node, "arguments")
        if callee is not None and spelling(callee, source) in {"require", "import"}:
            if arguments is not None and len(arguments.named_children) == 1:
                return arguments.named_children[0]
        return None


class RelativeImportResolver(ImportResolver):
    """Resolve JS-family relative specifiers with and without source extensions."""

    def names(self, dependency: Import, source: Source) -> tuple[str, ...]:
        module = dependency.module
        if not module.startswith("."):
            return (module,)
        normalized = posixpath.normpath(posixpath.join(posixpath.dirname(source.path), module))
        stem, extension = posixpath.splitext(normalized)
        if extension in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
            return module, normalized, stem
        return module, normalized
