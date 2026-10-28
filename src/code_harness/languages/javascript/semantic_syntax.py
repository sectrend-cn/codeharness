"""Javascript grammar interpretation for shared semantic analysis."""

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.languages.semantic_nodes import SemanticNodes
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.semantics.model import ImportedName, Symbol
from code_harness.semantics.results import ResultKind, ResultResolver


def _names(node: Node) -> tuple[Node, ...]:
    if node.type in {"identifier", "undefined", "shorthand_property_identifier_pattern"}:
        return (node,)
    target = (
        field(node, "value" if node.type == "pair_pattern" else "name")
        or field(node, "pattern")
        or field(node, "left")
    )
    if target is not None:
        return _names(target)
    return tuple(
        name
        for child in node.named_children
        if child != field(node, "type") and child != field(node, "value")
        for name in _names(child)
    )


class JavaScriptSemanticSyntax(SemanticNodes):
    """JS and TS share lexical parameter patterns and explicit exports."""

    identifiers = frozenset(
        {
            "identifier",
            "undefined",
            "shorthand_property_identifier",
            "shorthand_property_identifier_pattern",
        }
    )
    references = frozenset({"this", "type_identifier"})
    members = frozenset({"member_expression"})
    assignments = frozenset({"assignment_expression"})
    functions = frozenset(
        {
            "function_declaration",
            "function_expression",
            "generator_function_declaration",
            "generator_function",
            "arrow_function",
            "method_definition",
        }
    )
    classes = frozenset({"class_declaration", "class"})
    fields = frozenset({"public_field_definition", "field_definition"})
    declarations = frozenset({"variable_declarator"})
    destructuring = frozenset({"tuple_pattern", "list_pattern"})
    subscripts = frozenset({"subscript_expression"})
    wrappers = frozenset({"parenthesized_expression", "unary_expression"})
    constructors = frozenset({"call_expression", "new_expression"})
    iterations = frozenset({"for_statement", "for_in_statement"})
    annotations = frozenset({"type", "type_annotation", "type_arguments", "import_statement"})
    blocks = frozenset({"statement_block"})
    calls = frozenset({"call_expression", "new_expression"})
    receiver_names = ("this",)
    constructor_names = frozenset({"constructor"})
    broad_types = frozenset({"any", "unknown"})
    no_results = frozenset({"void", "undefined", "never"})
    outgoing_wrappers = frozenset(
        {"spread_element", "unary_expression", "parenthesized_expression"}
    )
    variadic_patterns = frozenset({"rest_pattern"})
    dictionary_prefixes = ("Record<", "{[key:")

    block_scopes = frozenset({"statement_block", "catch_clause"})

    def base_receiver(self, node: Node) -> bool:
        return node.type == "super"

    def static_member(self, node: Node) -> bool:
        return any(child.type == "static" for child in node.children)

    def inherited_types(self, node: Node) -> tuple[Node, ...]:
        heritage = next((n for n in node.named_children if n.type == "class_heritage"), None)
        return tuple(heritage.named_children) if heritage is not None else ()

    def call_result(self, call: Node, symbol: Symbol, results: ResultResolver) -> ResultKind:
        function = symbol.value
        if function is not None and self._deferred_result(function):
            return ResultKind.VALUE
        if function is not None and symbol.annotation is None:
            values = self.returned_values(function)
            if len(values) == 1:
                forwarded = self._forwarded_callback(values[0], function, call, results)
                if forwarded is not None:
                    return results.callback(forwarded)
        return super().call_result(call, symbol, results)

    def _forwarded_callback(
        self, value: Node, function: Node, call: Node, results: ResultResolver
    ) -> Node | None:
        callee = self.call(value)
        if callee is None or callee.type != "identifier":
            return None
        binding = results.index_for(callee).resolve(callee)
        if binding is None or binding.kind != "parameter" or binding.writes:
            return None
        if not self._simple_parameters(function):
            return None
        arguments = self.arguments(call)
        for position, parameter in enumerate(self.parameters(function)):
            if parameter == binding.node and position < len(arguments):
                return arguments[position]
        return None

    def _simple_parameters(self, function: Node) -> bool:
        parameters = field(function, "parameters")
        if parameters is None:
            return False
        return not any(
            node.type in {"object_pattern", "array_pattern", "rest_pattern"}
            for node in walk(parameters)
        )

    def callback_result(
        self, node: Node | None, annotation: Node | None, results: ResultResolver
    ) -> ResultKind:
        if node is not None and node.parent is not None:
            if node.parent.type == "variable_declarator":
                annotation = annotation or field(node.parent, "type")
        if annotation is not None:
            contract = self._result_type(annotation)
            if contract.type != "function_type":
                return ResultKind.UNRESOLVED
            result = field(contract, "return_type")
            return self._annotated_result(result)
        return self._callback_body_result(node, results)

    def _callback_body_result(self, node: Node | None, results: ResultResolver) -> ResultKind:
        if node is None or not self.function(node):
            return ResultKind.UNRESOLVED
        if self._deferred_result(node):
            return ResultKind.VALUE
        declared = self.result_annotation(node)
        if declared is not None:
            return self._annotated_result(declared)
        if field(node, "body") is None:
            return ResultKind.UNRESOLVED
        values = tuple(results.expression(value) for value in self.returned_values(node))
        if ResultKind.VALUE in values:
            return ResultKind.VALUE
        return ResultKind.UNRESOLVED if ResultKind.UNRESOLVED in values else ResultKind.NONE

    def _deferred_result(self, node: Node) -> bool:
        return "generator" in node.type or any(child.type == "async" for child in node.children)

    def _result_type(self, node: Node) -> Node:
        wrappers = {"type_annotation", "parenthesized_type"}
        while node.type in wrappers and node.named_child_count == 1:
            node = node.named_children[0]
        return node

    def _annotated_result(self, node: Node | None) -> ResultKind:
        if node is None:
            return ResultKind.UNRESOLVED
        node = self._result_type(node)
        if node.text in {b"void", b"undefined", b"never"}:
            return ResultKind.NONE
        if node.type == "type_identifier" or node.text in {b"any", b"unknown"}:
            return ResultKind.UNRESOLVED
        return ResultKind.VALUE

    def expression_result(self, node: Node, results: ResultResolver) -> ResultKind:
        if node.type == "parenthesized_expression" and node.named_child_count == 1:
            return results.expression(node.named_children[0])
        if node.type == "unary_expression" and any(c.type == "void" for c in node.children):
            return ResultKind.NONE
        if node.type in {
            "number",
            "string",
            "template_string",
            "object",
            "array",
            "true",
            "false",
            "null",
            "binary_expression",
            "assignment_expression",
            "augmented_assignment_expression",
            "update_expression",
            "arrow_function",
            "function_expression",
            "new_expression",
        }:
            return ResultKind.VALUE
        return ResultKind.UNRESOLVED

    def assignment(self, node: Node) -> tuple[Node | None, Node | None]:
        if node.type == "catch_clause":
            return field(node, "parameter"), None
        return super().assignment(node)

    def assignment_targets(self, node: Node) -> tuple[Node, ...]:
        if node.type in {"object_pattern", "array_pattern"}:
            return _names(node)
        return super().assignment_targets(node)

    def declares_local(self, node: Node) -> bool:
        parent = node.parent
        while parent is not None and parent.type in {
            "object_pattern",
            "array_pattern",
            "pair_pattern",
            "rest_pattern",
            "assignment_pattern",
        }:
            parent = parent.parent
        return parent is not None and parent.type in {"variable_declarator", "catch_clause"}

    def input_container(self, node: Node, parent: Node) -> bool:
        if parent.type == "ternary_expression":
            return node in (field(parent, "consequence"), field(parent, "alternative"))
        if parent.type == "pair":
            return field(parent, "value") == node
        return parent.type in {"object", "array", "parenthesized_expression"}

    def forwarded_assignment(self, node: Node) -> Node | None:
        parent = node.parent
        if parent is None:
            return None
        if parent.type == "variable_declarator" and field(parent, "value") == node:
            return field(parent, "name")
        if parent.type == "assignment_expression" and field(parent, "right") == node:
            return field(parent, "left")
        return None

    def package(self, context: TreeContext) -> str:
        return context.source.path

    def parameters(self, node: Node) -> tuple[Node, ...]:
        parameters = field(node, "parameters") or field(node, "parameter")
        return _names(parameters) if parameters is not None else ()

    def exported(self, node: Node, name: str, context: TreeContext) -> bool:
        if context.source.path.endswith(".d.ts"):
            return True
        current: Node | None = node
        while current is not None and current.type != "program":
            if current.type == "export_statement":
                return True
            current = current.parent
        return name == "constructor"

    def imports(self, context: TreeContext) -> tuple[ImportedName, ...]:
        result = list(self._requires(context))
        for node in walk(context.root):
            source = field(node, "source") if node.type == "import_statement" else None
            if source is None:
                continue
            module = spelling(source, context.source)[1:-1]
            result.extend(self._bindings(node, module, context))
        return tuple(result)

    def _bindings(self, node: Node, module: str, context: TreeContext) -> tuple[ImportedName, ...]:
        result: list[ImportedName] = []
        for child in walk(node):
            if child.type == "import_specifier":
                alias = field(child, "alias") or field(child, "name")
                if alias is not None:
                    result.append(
                        ImportedName(
                            spelling(alias, context.source),
                            module,
                            alias,
                            spelling(field(child, "name") or alias, context.source),
                        )
                    )
            elif child.type in {"import_clause", "namespace_import"}:
                result.extend(
                    ImportedName(spelling(name, context.source), module, name)
                    for name in child.named_children
                    if name.type == "identifier"
                )
        return tuple(result)

    def _requires(self, context: TreeContext) -> tuple[ImportedName, ...]:
        result: list[ImportedName] = []
        for node in walk(context.root):
            if node.type != "variable_declarator":
                continue
            value, name = field(node, "value"), field(node, "name")
            if value is not None and name is not None:
                result.extend(self._require_binding(value, name, context))
        return tuple(result)

    def _require_binding(
        self, value: Node, name: Node, context: TreeContext
    ) -> tuple[ImportedName, ...]:
        callee, arguments = field(value, "function"), field(value, "arguments")
        if callee is None or spelling(callee, context.source) != "require":
            return ()
        if arguments is None or arguments.named_child_count != 1:
            return ()
        literal = arguments.named_children[0]
        if literal.type != "string":
            return ()
        module = spelling(literal, context.source)[1:-1]
        return tuple(
            ImportedName(spelling(binding, context.source), module, binding)
            for binding in _names(name)
        )
