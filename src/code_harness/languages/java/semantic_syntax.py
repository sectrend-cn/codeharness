"""Java grammar interpretation for shared lexical and project usage evidence."""

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.languages.semantic_nodes import SemanticNodes
from code_harness.parsing.treesitter import field, spelling
from code_harness.semantics.model import ImportedName, Symbol


class JavaSemanticSyntax(SemanticNodes):
    """Resolve explicit Java bindings without claiming compiler overload resolution."""

    references = frozenset({"this", "type_identifier"})
    members = frozenset({"field_access", "method_reference"})
    assignments = frozenset({"assignment_expression"})
    functions = frozenset(
        {
            "method_declaration",
            "constructor_declaration",
            "compact_constructor_declaration",
            "lambda_expression",
        }
    )
    classes = frozenset(
        {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
    )
    declarations = frozenset({"variable_declarator"})
    constructors = frozenset({"object_creation_expression"})
    annotations = frozenset(
        {
            "type_arguments",
            "import_declaration",
            "package_declaration",
            "annotation",
            "marker_annotation",
        }
    )
    blocks = frozenset({"block", "constructor_body"})
    block_scopes = frozenset({"block", "for_statement", "enhanced_for_statement", "catch_clause"})
    receiver_names = ("this",)
    no_results = frozenset({"void"})
    broad_types = frozenset({"Object", "?"})
    variadic_patterns = frozenset({"spread_parameter"})

    def base_receiver(self, node: Node) -> bool:
        return node.type == "super"

    def static_member(self, node: Node) -> bool:
        modifiers = next((n for n in node.named_children if n.type == "modifiers"), None)
        return modifiers is not None and any(n.type == "static" for n in modifiers.children)

    def input_container(self, node: Node, parent: Node) -> bool:
        if parent.type == "ternary_expression":
            return node in (field(parent, "consequence"), field(parent, "alternative"))
        return super().input_container(node, parent)

    def forwarded_assignment(self, node: Node) -> Node | None:
        parent = node.parent
        if parent is not None and parent.type == "variable_declarator":
            return field(parent, "name") if field(parent, "value") == node else None
        return super().forwarded_assignment(node)

    def parameters(self, node: Node) -> tuple[Node, ...]:
        parameters = field(node, "parameters")
        if parameters is None:
            return ()
        if parameters.type == "identifier":
            return (parameters,)
        return tuple(
            name
            for parameter in parameters.named_children
            if (name := self._parameter_name(parameter)) is not None
        )

    def _parameter_name(self, parameter: Node) -> Node | None:
        if parameter.type == "receiver_parameter":
            return None
        if parameter.type == "identifier":
            return parameter
        if parameter.type == "spread_parameter":
            declarator = next(
                (n for n in parameter.named_children if n.type == "variable_declarator"), None
            )
            return field(declarator, "name") if declarator is not None else None
        return field(parameter, "name")

    def function_name(self, node: Node) -> Node | None:
        return field(node, "name") if node.type == "method_declaration" else None

    def result_annotation(self, node: Node) -> Node | None:
        return field(node, "type") if node.type == "method_declaration" else None

    def field_names(self, node: Node) -> tuple[Node, ...]:
        if node.type != "variable_declarator" or node.parent is None:
            return ()
        name = field(node, "name")
        return (name,) if node.parent.type == "field_declaration" and name is not None else ()

    def annotation(self, node: Node) -> Node | None:
        if node.type == "variable_declarator" and node.parent is not None:
            return field(node.parent, "type")
        return super().annotation(node)

    def assignment(self, node: Node) -> tuple[Node | None, Node | None]:
        if node.type in {"enhanced_for_statement", "catch_formal_parameter"}:
            return field(node, "name"), None
        if node.type == "variable_declarator" and node.parent is not None:
            if node.parent.type == "spread_parameter":
                return None, None
        return super().assignment(node)

    def member_expression(self, node: Node) -> bool:
        return super().member_expression(node) or (
            node.type == "method_invocation" and field(node, "object") is not None
        )

    def member_parts(self, node: Node) -> tuple[Node | None, Node | None]:
        if node.type == "method_reference" and len(node.named_children) >= 2:
            return node.named_children[0], node.named_children[-1]
        if node.type == "method_invocation":
            return field(node, "object"), field(node, "name")
        return super().member_parts(node)

    def call(self, node: Node) -> Node | None:
        if node.type == "object_creation_expression":
            return field(node, "type")
        if node.type == "method_invocation":
            return node if field(node, "object") is not None else field(node, "name")
        return None

    def read(self, node: Node) -> bool:
        parent = node.parent
        if parent is not None and parent.type == "assignment_expression":
            if field(parent, "left") == node:
                operator = field(parent, "operator")
                return operator is not None and operator.type != "="
        return super().read(node)

    def declares_local(self, node: Node) -> bool:
        parent = node.parent
        return super().declares_local(node) or (
            parent is not None
            and parent.type in {"enhanced_for_statement", "catch_formal_parameter"}
        )

    def has_result(self, symbol: Symbol) -> bool:
        method = symbol.value
        if method is None or method.parent is None:
            return super().has_result(symbol)
        siblings = method.parent.named_children
        return super().has_result(symbol) and not any(
            sibling.type == "method_declaration"
            and (name := field(sibling, "name")) is not None
            and name.text == symbol.node.text
            and (result := field(sibling, "type")) is not None
            and result.type == "void_type"
            for sibling in siblings
        )

    def inherited_types(self, node: Node) -> tuple[Node, ...]:
        return tuple(
            base.named_children[0] if base.type == "generic_type" else base
            for child in node.named_children
            if child.type in {"superclass", "super_interfaces", "extends_interfaces"}
            for group in child.named_children
            for base in (group.named_children if group.type == "type_list" else [group])
        )

    def typed_construction(self, node: Node) -> bool:
        return node.type == "object_creation_expression"

    def exported(self, node: Node, name: str, context: TreeContext) -> bool:
        if len(self._overloads(node, name, context)) > 1:
            return True
        modifiers = next(
            (child for child in node.named_children if child.type == "modifiers"), None
        )
        if modifiers is None:
            return True
        if any(
            child.type in {"annotation", "marker_annotation"} for child in modifiers.named_children
        ):
            return True
        return not any(child.type == "private" for child in modifiers.children)

    def _overloads(self, node: Node, name: str, context: TreeContext) -> tuple[Node, ...]:
        parent = node.parent
        if parent is None:
            return ()
        return tuple(
            sibling
            for sibling in parent.named_children
            if sibling.type == "method_declaration"
            and (declared := field(sibling, "name")) is not None
            and spelling(declared, context.source) == name
        )

    def package(self, context: TreeContext) -> str:
        declaration = next(
            (n for n in context.root.named_children if n.type == "package_declaration"), None
        )
        if declaration is None:
            return ""
        name = next(
            (
                n
                for n in declaration.named_children
                if n.type in {"identifier", "scoped_identifier"}
            ),
            None,
        )
        return spelling(name, context.source) if name is not None else ""

    def module_names(self, context: TreeContext) -> tuple[str, ...]:
        package = self.package(context)
        return tuple(
            ".".join(part for part in (package, spelling(name, context.source)) if part)
            for node in context.root.named_children
            if (name := self.class_name(node)) is not None
        )

    def imports(self, context: TreeContext) -> tuple[ImportedName, ...]:
        result: list[ImportedName] = []
        for node in context.root.named_children:
            if node.type != "import_declaration":
                continue
            if any(child.type == "asterisk" for child in node.named_children):
                continue
            target = next(
                (n for n in node.named_children if n.type in {"identifier", "scoped_identifier"}),
                None,
            )
            if target is not None:
                module = spelling(target, context.source)
                name = field(target, "name") or target
                result.append(ImportedName(spelling(name, context.source), module, name))
        return tuple(result)
