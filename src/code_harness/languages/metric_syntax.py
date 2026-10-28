"""Grammar interpretation for built-in function and control-flow syntax."""

from __future__ import annotations

from tree_sitter import Node

from code_harness.parsing.treesitter import field, spelling
from code_harness.source import Source

FUNCTIONS = frozenset(
    {
        "function_definition",
        "lambda",
        "function_declaration",
        "method_declaration",
        "func_literal",
        "function_expression",
        "generator_function_declaration",
        "generator_function",
        "arrow_function",
        "method_definition",
    }
)


_CONTROL = frozenset(
    {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "do_statement",
        "for_in_statement",
        "try_statement",
        "except_clause",
        "catch_clause",
        "switch_statement",
        "expression_switch_statement",
        "type_switch_statement",
        "select_statement",
        "with_statement",
        "for_in_clause",
    }
)
_DECISIONS = (
    _CONTROL
    - {
        "try_statement",
        "with_statement",
        "switch_statement",
        "expression_switch_statement",
        "type_switch_statement",
        "select_statement",
    }
) | frozenset(
    {
        "conditional_expression",
        "ternary_expression",
        "case_clause",
        "switch_case",
        "expression_case",
        "type_case",
        "communication_case",
        "if_clause",
    }
)


def _control_depth(node: Node, depth: int) -> int:
    if node.type == "elif_clause":
        return depth
    return depth + int(node.type in _CONTROL)


def _short_circuit(node: Node, source: Source) -> bool:
    if node.type not in {"binary_expression", "binary_operator", "boolean_operator"}:
        return False
    operator = field(node, "operator")
    return operator is not None and spelling(operator, source) in {"and", "or", "&&", "||", "??"}


def _parameters(node: Node, source: Source, semantics: GrammarMetrics) -> int:
    parameters = field(node, "parameters")
    if parameters is None:
        return int(field(node, "parameter") is not None)
    count = 0
    for parameter in parameters.named_children:
        if parameter.type in {"comment", "positional_separator", "keyword_separator"}:
            continue
        count += semantics.parameter_count(parameter, source)
    return count


class GrammarMetrics:
    """Count each named parameter and retain all string expression lines."""

    def is_function(self, node: Node) -> bool:
        return node.type in FUNCTIONS

    def body(self, node: Node) -> Node | None:
        return field(node, "body")

    def ignored_line(self, node: Node) -> bool:
        return node.type == "comment" or self.is_docstring(node)

    def parameters(self, node: Node, source: Source) -> int:
        return _parameters(node, source, self)

    def control_depth(self, node: Node, depth: int) -> int:
        return _control_depth(node, depth)

    def decisions(self, node: Node, source: Source) -> int:
        return int(node.type in _DECISIONS) + int(_short_circuit(node, source))

    def is_statement(self, node: Node) -> bool:
        return node.type.endswith("_statement") or node.type in {
            "short_var_declaration",
            "lexical_declaration",
            "variable_declaration",
            "var_declaration",
            "const_declaration",
            "raise_statement",
        }

    def is_docstring(self, node: Node) -> bool:
        return False

    def parameter_count(self, node: Node, source: Source) -> int:
        return 1
