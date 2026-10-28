"""Interpret built-in grammar constructs needed by object-design policy."""

from tree_sitter import Node

from code_harness.parsing.treesitter import field, spelling
from code_harness.source import Source


class GrammarDesignSyntax:
    """Classify identity comparisons and module-level function declarations."""

    def dispatch(self, node: Node, source: Source) -> bool:
        if node.type in {"match_statement", "switch_statement", "expression_switch_statement"}:
            subject = field(node, "subject") or field(node, "value") or field(node, "condition")
            return subject is not None and self._selector(subject, source)
        if node.type not in {"comparison_operator", "binary_expression", "binary_operator"}:
            return False
        children = node.named_children
        return any(self._selector(child, source) for child in children) and any(
            self._identity(child, source) for child in children
        )

    def _selector(self, node: Node, source: Source) -> bool:
        if node.type == "parenthesized_expression" and len(node.named_children) == 1:
            return self._selector(node.named_children[0], source)
        text = spelling(node, source)
        return text.rsplit(".", 1)[-1] in {"language", "rule_id"}

    def _identity(self, node: Node, source: Source) -> bool:
        if node.type in {"string", "interpreted_string_literal", "raw_string_literal"}:
            return True
        if node.type in {"attribute", "member_expression", "selector_expression"}:
            return spelling(node, source).rsplit(".", 1)[-1].isupper()
        if node.type in {"set", "tuple", "list"}:
            return any(self._identity(child, source) for child in node.named_children)
        return False

    def module_functions(self, root: Node) -> tuple[Node, ...]:
        functions: list[Node] = []
        for child in root.named_children:
            node = child
            if child.type in {"decorated_definition", "export_statement"}:
                node = field(child, "definition") or field(child, "declaration") or child
            functions.extend(self._module_functions(node))
        return tuple(functions)

    def function_name(self, node: Node) -> Node | None:
        return field(node, "name")

    def _module_functions(self, node: Node) -> tuple[Node, ...]:
        if node.type in {
            "function_definition",
            "function_declaration",
            "generator_function_declaration",
        }:
            return (node,)
        if node.type in {"lexical_declaration", "variable_declaration"}:
            return tuple(
                child
                for child in node.named_children
                if (value := field(child, "value")) is not None
                and value.type in {"arrow_function", "function_expression"}
            )
        return ()
