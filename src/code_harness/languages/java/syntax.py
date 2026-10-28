"""Java metrics, dependency and object-design grammar interpretation."""

from tree_sitter import Node

from code_harness.languages.design_syntax import GrammarDesignSyntax
from code_harness.languages.import_syntax import TreeImports
from code_harness.languages.metric_syntax import GrammarMetrics
from code_harness.parsing.treesitter import field, spelling
from code_harness.source import Source


class JavaMetrics(GrammarMetrics):
    """Measure Java executable declarations and isolate nested lambda decisions."""

    def is_function(self, node: Node) -> bool:
        return node.type in {
            "method_declaration",
            "constructor_declaration",
            "compact_constructor_declaration",
            "lambda_expression",
        }

    def ignored_line(self, node: Node) -> bool:
        return node.type in {"line_comment", "block_comment"}

    def parameters(self, node: Node, source: Source) -> int:
        parameters = field(node, "parameters")
        if parameters is None and node.type == "compact_constructor_declaration":
            owner = node.parent.parent if node.parent is not None else None
            parameters = field(owner, "parameters") if owner is not None else None
        if parameters is None:
            return 0
        if parameters.type == "identifier":
            return 1
        return sum(
            child.type not in {"receiver_parameter", "line_comment", "block_comment"}
            for child in parameters.named_children
        )

    def control_depth(self, node: Node, depth: int) -> int:
        if node.type in {
            "enhanced_for_statement",
            "switch_expression",
            "synchronized_statement",
            "try_with_resources_statement",
        }:
            return depth + 1
        return super().control_depth(node, depth)

    def decisions(self, node: Node, source: Source) -> int:
        if node.type == "switch_label":
            return int(any(child.type == "case" for child in node.children))
        return super().decisions(node, source) + int(node.type == "enhanced_for_statement")

    def is_statement(self, node: Node) -> bool:
        return super().is_statement(node) or node.type in {
            "local_variable_declaration",
            "explicit_constructor_invocation",
        }


class JavaImports(TreeImports):
    """Expose exact qualified import names, including static members and wildcards."""

    def _module_node(self, node: Node, source: Source) -> Node | None:
        return node if node.type == "import_declaration" else None

    def _literal(self, node: Node, source: Source) -> str | None:
        target = next(
            (
                child
                for child in node.named_children
                if child.type in {"identifier", "scoped_identifier"}
            ),
            None,
        )
        if target is None:
            return None
        suffix = ".*" if any(child.type == "asterisk" for child in node.named_children) else ""
        return spelling(target, source) + suffix


class JavaDesignSyntax(GrammarDesignSyntax):
    """Interpret Java switches, enum constants and string identity comparisons."""

    def dispatch(self, node: Node, source: Source) -> bool:
        if node.type == "method_invocation":
            return self._equals_dispatch(node, source)
        if node.type == "switch_expression":
            subject = field(node, "condition")
            return subject is not None and self._selector(subject, source)
        return super().dispatch(node, source)

    def _equals_dispatch(self, node: Node, source: Source) -> bool:
        name = field(node, "name")
        receiver = field(node, "object")
        arguments = field(node, "arguments")
        if name is None or receiver is None or arguments is None:
            return False
        if spelling(name, source) != "equals" or len(arguments.named_children) != 1:
            return False
        operands = (receiver, arguments.named_children[0])
        return any(self._selector(n, source) for n in operands) and any(
            self._identity(n, source) for n in operands
        )

    def _identity(self, node: Node, source: Source) -> bool:
        if node.type == "string_literal":
            return True
        if node.type == "field_access":
            return spelling(node, source).rsplit(".", 1)[-1].isupper()
        return super()._identity(node, source)
