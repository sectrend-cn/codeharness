"""Python grammar interpretation for shared semantic analysis."""

import posixpath

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.languages.python.result_syntax import PythonResultSyntax
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.semantics.model import ImportedName


def _names(node: Node) -> tuple[Node, ...]:
    if node.type in {"identifier", "shorthand_property_identifier_pattern"}:
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


class PythonSemanticSyntax(PythonResultSyntax):
    """Python public module APIs may be imported outside the selected snapshot."""

    functions = frozenset({"function_definition", "lambda"})
    members = frozenset({"attribute"})
    assignments = frozenset({"assignment"})
    classes = frozenset({"class_definition"})
    destructuring = frozenset({"expression_list", "pattern_list", "tuple_pattern", "list_pattern"})
    subscripts = frozenset({"subscript"})
    wrappers = frozenset({"parenthesized_expression", "unary_expression"})
    constructors = frozenset({"call"})
    iterations = frozenset({"for_statement", "for_in_clause"})
    annotations = frozenset(
        {"type", "type_annotation", "type_arguments", "import_statement", "import_from_statement"}
    )
    blocks = frozenset({"block"})
    calls = frozenset({"call"})
    receiver_names = ("self", "cls")
    abstract_names = frozenset({"Protocol"})
    collection_methods = frozenset({"values", "items"})
    constructor_names = frozenset({"__init__", "__new__"})
    builtin_converters = frozenset({"int", "str", "float", "bool", "bytes"})
    broad_types = frozenset({"Any", "object"})
    no_results = frozenset({"None", "NoReturn"})
    outgoing_wrappers = frozenset(
        {
            "expression_list",
            "dictionary_splat",
            "list_splat",
            "keyword_argument",
            "unary_expression",
            "parenthesized_expression",
        }
    )
    variadic_patterns = frozenset({"list_splat_pattern"})
    dictionary_names = frozenset({"dict", "Dict", "Mapping"})
    dictionary_prefixes = ("dict[", "Dict[", "Mapping[")

    block_scopes = frozenset[str]()

    def value_type_node(self, node: Node) -> Node | None:
        """Use only the first list element's explicit constructor name as evidence."""
        if node.type != "list":
            return None
        first = next((child for child in node.named_children if child.type != "comment"), None)
        if first is None or first.type != "call":
            return None
        name = field(first, "function")
        return name if name is not None and name.type == "identifier" else None

    def inherited_types(self, node: Node) -> tuple[Node, ...]:
        bases = field(node, "superclasses")
        return (
            tuple(
                field(base, "value") or base
                for base in bases.named_children
                if base.type != "keyword_argument"
            )
            if bases is not None
            else ()
        )

    def base_receiver(self, node: Node) -> bool:
        callee, arguments = field(node, "function"), field(node, "arguments")
        return (
            node.type == "call"
            and callee is not None
            and callee.text == b"super"
            and arguments is not None
            and arguments.named_child_count == 0
        )

    def static_member(self, node: Node) -> bool:
        parent = node.parent
        return (
            parent is not None
            and parent.type == "decorated_definition"
            and any(
                child.type == "decorator" and child.text == b"@staticmethod"
                for child in parent.named_children
            )
        )

    def shared_member_namespace(self) -> bool:
        return True

    def input_container(self, node: Node, parent: Node) -> bool:
        if parent.type == "conditional_expression":
            branches = [child for child in parent.named_children if child.type != "comment"]
            return len(branches) == 3 and node in (branches[0], branches[2])
        return super().input_container(node, parent)

    def result_consumed(self, node: Node) -> bool:
        """Decorator factories supply declaration behavior, not application payloads."""
        if node.parent is not None and node.parent.type == "decorator":
            return False
        return super().result_consumed(node)

    def package(self, context: TreeContext) -> str:
        return context.source.path

    def parameters(self, node: Node) -> tuple[Node, ...]:
        parameters = field(node, "parameters")
        return _names(parameters) if parameters is not None else ()

    def exported(self, node: Node, name: str, context: TreeContext) -> bool:
        if context.source.path.endswith(".pyi"):
            return True
        if name.startswith("__") and name.endswith("__"):
            return True
        parent = node.parent
        if parent is not None and parent.type == "decorated_definition":
            return True
        return parent is not None and parent.type == "module" and not name.startswith("_")

    def imports(self, context: TreeContext) -> tuple[ImportedName, ...]:
        result: list[ImportedName] = []
        for node in walk(context.root):
            if node.type not in {"import_statement", "import_from_statement"}:
                continue
            module = field(node, "module_name")
            prefix = spelling(module, context.source) if module is not None else ""
            prefix = self._module(prefix, context)
            for entry in node.children_by_field_name("name"):
                target = field(entry, "name") or entry
                alias = field(entry, "alias")
                name = spelling(alias or target, context.source)
                origin = prefix or spelling(target, context.source)
                result.append(
                    ImportedName(
                        name.split(".")[0],
                        origin,
                        alias or target,
                        spelling(target, context.source),
                    )
                )
        return tuple(result)

    def _module(self, name: str, context: TreeContext) -> str:
        level = len(name) - len(name.lstrip("."))
        if not level:
            return name
        parts = context.source.path.split("/")[:-level]
        return ".".join((*parts, name[level:])).rstrip(".")

    def module_names(self, context: TreeContext) -> tuple[str, ...]:
        path = posixpath.splitext(context.source.path)[0]
        names = (path, path.replace("/", "."), path.removeprefix("src/").replace("/", "."))
        return tuple(name.removesuffix(".__init__") for name in names)
