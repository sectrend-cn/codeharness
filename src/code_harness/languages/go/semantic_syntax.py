"""Go grammar interpretation for shared semantic analysis."""

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.languages.semantic_nodes import SemanticNodes
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.semantics.model import ImportedName


class GoSemanticSyntax(SemanticNodes):
    """Go exported names and runtime entry points retain external callers."""

    references = frozenset({"type_identifier"})
    members = frozenset({"selector_expression"})
    assignments = frozenset({"assignment_statement", "short_var_declaration"})
    functions = frozenset({"function_declaration", "method_declaration", "func_literal"})
    classes = frozenset({"type_spec"})
    fields = frozenset({"field_declaration"})
    declarations = frozenset({"var_spec", "const_spec"})
    destructuring = frozenset({"expression_list"})
    subscripts = frozenset({"index_expression"})
    wrappers = frozenset({"parenthesized_expression", "unary_expression", "pointer_expression"})
    constructors = frozenset({"call_expression", "composite_literal"})
    iterations = frozenset({"for_statement"})
    annotations = frozenset({"type", "type_arguments", "import_spec"})
    blocks = frozenset({"block"})
    calls = frozenset({"call_expression"})
    broad_types = frozenset({"any", "interface{}"})
    no_results = frozenset({"()"})
    outgoing_wrappers = frozenset(
        {"expression_list", "variadic_argument", "unary_expression", "parenthesized_expression"}
    )
    variadic_patterns = frozenset({"variadic_parameter_declaration"})
    dictionary_prefixes = ("map[",)

    block_scopes = frozenset({"block"})

    def input_container(self, node: Node, parent: Node) -> bool:
        if parent.type == "expression_list":
            return parent.named_children == [node]
        return super().input_container(node, parent)

    def forwarded_assignment(self, node: Node) -> Node | None:
        parent = node.parent
        if parent is None or parent.type not in self.assignments | self.declarations:
            return None
        target, value = self.assignment(parent)
        if value != node or target is None:
            return None
        return self.single_value(target)

    def value_type_node(self, node: Node) -> Node | None:
        """Composite literals, make and new spell the type beside the value."""
        current = node
        while current.type in self.wrappers:
            wrapped = self.wrapped_value(current)
            if wrapped is None:
                return None
            current = wrapped
        if current.type == "composite_literal":
            return field(current, "type")
        if current.type in self.calls:
            return self._builtin_type_argument(current)
        return None

    def _builtin_type_argument(self, node: Node) -> Node | None:
        callee = field(node, "function")
        if callee is None or not self.identifier(callee):
            return None
        if callee.text not in {b"make", b"new"}:
            return None
        arguments = field(node, "arguments")
        if arguments is None:
            return None
        return next(
            (
                child
                for child in arguments.named_children
                if child.type not in self.nonvalue_children
            ),
            None,
        )

    def element_type(self, node: Node) -> Node | None:
        """Reduce map values and slice, array and pointer elements to the final type."""
        current = node
        reduced: Node | None = None
        while (child := self._element_child(current)) is not None:
            current = child
            reduced = child
        return reduced

    def _element_child(self, node: Node) -> Node | None:
        if node.type == "map_type":
            return field(node, "value")
        if node.type in {"slice_type", "array_type"}:
            return field(node, "element")
        if node.type in {"pointer_type", "parenthesized_type"}:
            children = [
                child for child in node.named_children if child.type not in self.nonvalue_children
            ]
            return children[0] if len(children) == 1 else None
        return None

    def package(self, context: TreeContext) -> str:
        return next(
            (
                spelling(node, context.source)
                for node in context.root.named_children
                if node.type == "package_clause"
            ),
            "",
        )

    def parameters(self, node: Node) -> tuple[Node, ...]:
        parameters = field(node, "parameters")
        if parameters is None:
            return ()
        return tuple(
            name
            for parameter in parameters.named_children
            for name in parameter.children_by_field_name("name")
        )

    def exported(self, node: Node, name: str, context: TreeContext) -> bool:
        if node.type == "func_literal":
            return False
        return (
            name[:1].isupper()
            or name == "init"
            or (name == "main" and self.package(context) == "package main")
        )

    def imports(self, context: TreeContext) -> tuple[ImportedName, ...]:
        result: list[ImportedName] = []
        for node in walk(context.root):
            path = field(node, "path") if node.type == "import_spec" else None
            if path is None:
                continue
            module = spelling(path, context.source)[1:-1]
            alias = field(node, "name")
            name = (
                spelling(alias, context.source) if alias is not None else module.rsplit("/", 1)[-1]
            )
            result.append(ImportedName(name, module, alias or path))
        return tuple(result)
