"""TypeScript abstract owners, inherited contracts and constructor properties."""

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.languages.javascript.semantic_syntax import JavaScriptSemanticSyntax
from code_harness.languages.typescript.result_syntax import TypeScriptResultSyntax
from code_harness.parsing.treesitter import field, spelling


class TypeScriptSemanticSyntax(TypeScriptResultSyntax):
    """Retain abstract class and method identities in the shared semantic index."""

    classes = JavaScriptSemanticSyntax.classes | {"abstract_class_declaration"}
    functions = JavaScriptSemanticSyntax.functions | {"abstract_method_signature"}

    def inherited_types(self, node: Node) -> tuple[Node, ...]:
        result: list[Node] = []
        for clause in super().inherited_types(node):
            if clause.type == "extends_clause":
                result.extend(clause.children_by_field_name("value"))
            elif clause.type == "implements_clause":
                result.extend(field(child, "name") or child for child in clause.named_children)
        return tuple(result)

    def parameter_property_syntax(self) -> "TypeScriptParameterPropertySyntax":
        return TypeScriptParameterPropertySyntax()


class TypeScriptParameterPropertySyntax(TypeScriptSemanticSyntax):
    """Interpret constructor properties and their branch-local receiver evidence."""

    def parameter_property(self, node: Node, function: Node, context: TreeContext) -> bool:
        name = field(function, "name")
        if function.type != "method_definition" or name is None:
            return False
        if spelling(name, context.source) != "constructor":
            return False
        parameter = node.parent
        if parameter is None or parameter.parent != field(function, "parameters"):
            return False
        return (
            parameter.type in {"required_parameter", "optional_parameter"}
            and field(parameter, "pattern") == node
            and any(
                child.type in {"accessibility_modifier", "readonly"} for child in parameter.children
            )
        )

    def narrowed_instances(self, node: Node) -> tuple[tuple[Node, Node], ...]:
        """Expose positive instanceof branches without crossing function boundaries."""
        result: list[tuple[Node, Node]] = []
        current = node
        while current.parent is not None and not self.function(current.parent):
            parent = current.parent
            if parent.type in {"ternary_expression", "if_statement"} and current == field(
                parent, "consequence"
            ):
                guard = self._instance_guard(field(parent, "condition"))
                if guard is not None:
                    result.append(guard)
            current = parent
        return tuple(result)

    def _instance_guard(self, node: Node | None) -> tuple[Node, Node] | None:
        if node is None:
            return None
        if node.type == "parenthesized_expression" and node.named_child_count == 1:
            return self._instance_guard(node.named_children[0])
        operator = field(node, "operator")
        if node.type != "binary_expression" or operator is None or operator.type != "instanceof":
            return None
        binding, declared = field(node, "left"), field(node, "right")
        if binding is None or declared is None or not self.identifier(binding):
            return None
        return binding, declared

    def conditional_branches(self, node: Node) -> tuple[Node, ...]:
        if node.type != "ternary_expression":
            return ()
        consequence, alternative = field(node, "consequence"), field(node, "alternative")
        if consequence is None or alternative is None:
            return ()
        return consequence, alternative
