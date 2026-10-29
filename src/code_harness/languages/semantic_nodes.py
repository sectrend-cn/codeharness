"""Reusable tree grammar interpretation for registered semantic adapters."""

import posixpath
from abc import ABC, abstractmethod

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.semantics.model import ImportedName, ParameterSlot, SemanticSyntax, Symbol
from code_harness.semantics.results import ResultKind, ResultResolver


class SemanticNodes(ABC):
    """Interpret grammar constructs while resolution remains with semantic consumers."""

    block_scopes = frozenset[str]()
    identifiers = frozenset({"identifier"})
    references = frozenset[str]()
    members = frozenset[str]()
    assignments = frozenset[str]()
    functions = frozenset[str]()
    classes = frozenset[str]()
    fields = frozenset[str]()
    declarations = frozenset[str]()
    destructuring = frozenset[str]()
    subscripts = frozenset[str]()
    wrappers = frozenset({"parenthesized_expression"})
    constructors = frozenset[str]()
    iterations = frozenset[str]()
    annotations = frozenset[str]()
    blocks = frozenset[str]()
    calls = frozenset[str]()
    receiver_names: tuple[str, ...] = ()
    abstract_names = frozenset[str]()
    collection_methods = frozenset[str]()
    constructor_names = frozenset[str]()
    builtin_converters = frozenset[str]()
    broad_types = frozenset[str]()
    no_results = frozenset[str]()
    outgoing_wrappers = frozenset[str]()
    variadic_patterns = frozenset[str]()
    dictionary_names = frozenset[str]()
    dictionary_prefixes: tuple[str, ...] = ()
    nonvalue_children = frozenset({"comment"})

    def identifier(self, node: Node) -> bool:
        return node.type in self.identifiers

    def reference(self, node: Node) -> bool:
        return self.identifier(node) or node.type in self.references

    def member_expression(self, node: Node) -> bool:
        return node.type in self.members

    def function(self, node: Node) -> bool:
        return node.type in self.functions

    def class_name(self, node: Node) -> Node | None:
        return field(node, "name") if node.type in self.classes else None

    def block_scope(self, node: Node) -> bool:
        return (
            node.type in self.block_scopes
            and node.parent is not None
            and not self.function(node.parent)
        )

    def field_names(self, node: Node) -> tuple[Node, ...]:
        if node.type not in self.fields:
            return ()
        return tuple(node.children_by_field_name("name") or node.children_by_field_name("property"))

    def annotation(self, node: Node) -> Node | None:
        return field(node, "type")

    def value(self, node: Node) -> Node | None:
        return field(node, "value")

    def function_name(self, node: Node) -> Node | None:
        name = field(node, "name")
        parent = node.parent
        if name is None and parent is not None and parent.type == "variable_declarator":
            return field(parent, "name")
        return name

    def result_annotation(self, node: Node) -> Node | None:
        return field(node, "return_type") or field(node, "result")

    def parameter_annotation(self, node: Node, stop: Node) -> Node | None:
        current: Node | None = node
        while current is not None and current != stop:
            annotation = field(current, "type")
            if annotation is not None:
                return annotation
            current = current.parent
        return None

    def parameter_property_syntax(self) -> SemanticSyntax | None:
        """Opt in to a separate constructor-property evidence graph when supported."""
        return None

    def parameter_property(self, node: Node, function: Node, context: TreeContext) -> bool:
        """Ordinary parameters do not also declare instance members."""
        return False

    def narrowed_instances(self, node: Node) -> tuple[tuple[Node, Node], ...]:
        """No branch-local instance guards are provided by default."""
        return ()

    def conditional_branches(self, node: Node) -> tuple[Node, ...]:
        """No conditional value alternatives are provided by default."""
        return ()

    def implicit_receivers(self) -> tuple[str, ...]:
        return self.receiver_names

    def receivers(self, node: Node) -> tuple[tuple[Node, Node | None], ...]:
        receiver = field(node, "receiver")
        if receiver is None:
            return ()
        return tuple(
            (name, field(entry, "type"))
            for entry in receiver.named_children
            for name in entry.children_by_field_name("name")
        )

    def assignment(self, node: Node) -> tuple[Node | None, Node | None]:
        if node.type in self.assignments:
            return field(node, "left"), field(node, "right")
        if node.type in self.declarations:
            return field(node, "name"), field(node, "value")
        return None, None

    def assignment_targets(self, node: Node) -> tuple[Node, ...]:
        if node.type in self.destructuring:
            return tuple(node.named_children)
        return (node,)

    def declares_local(self, node: Node) -> bool:
        return node.parent is not None and node.parent.type == "variable_declarator"

    def wrapped_value(self, node: Node) -> Node | None:
        if node.type in self.subscripts:
            return field(node, "value") or field(node, "object") or field(node, "operand")
        if node.type in self.wrappers:
            values = [
                child for child in node.named_children if child.type not in self.nonvalue_children
            ]
            return values[-1] if values else None
        return None

    def element_target(self, node: Node) -> bool:
        """Report assignment targets addressing one element of a bound container."""
        return self.single_value(node).type in self.subscripts

    def single_value(self, node: Node) -> Node:
        if node.type in {"expression_list", "parenthesized_expression"}:
            values = [
                child for child in node.named_children if child.type not in self.nonvalue_children
            ]
            if len(values) == 1:
                return self.single_value(values[0])
        return node

    def value_type_node(self, node: Node) -> Node | None:
        """Languages opt in to type expressions written beside their values."""
        return None

    def element_type(self, node: Node) -> Node | None:
        """Languages opt in to reducing container annotations to their element type."""
        return None

    def is_call(self, node: Node) -> bool:
        """Report call syntax; languages without calls answer no."""
        return node.type in self.calls

    def constructor(self, node: Node) -> Node | None:
        if node.type in self.constructors:
            return field(node, "function") or field(node, "constructor") or field(node, "type")
        return None

    def member_parts(self, node: Node) -> tuple[Node | None, Node | None]:
        return field(node, "object") or field(node, "operand"), field(node, "attribute") or field(
            node, "property"
        ) or field(node, "field")

    def inherited_types(self, node: Node) -> tuple[Node, ...]:
        inherited = (
            field(node, "superclasses")
            or field(node, "superclass")
            or next(
                (child for child in node.named_children if child.type == "class_heritage"), None
            )
        )

        return (inherited,) if inherited is not None else ()

    def base_receiver(self, node: Node) -> bool:
        """Languages opt in to lexical superclass receiver syntax."""
        return False

    def static_member(self, node: Node) -> bool:
        """Languages opt in to members outside instance override dispatch."""
        return False

    def shared_member_namespace(self) -> bool:
        """Static and instance methods occupy separate namespaces by default."""
        return False

    def abstract_base(self, name: str) -> bool:
        return name in self.abstract_names

    def iteration(self, node: Node) -> tuple[tuple[Node, ...], Node | None]:
        if node.type not in self.iterations:
            return (), None
        target = field(node, "left")
        if target is None:
            return (), None
        targets = tuple(target.named_children) if target.type == "pattern_list" else (target,)
        return targets, field(node, "right")

    def in_annotation(self, node: Node) -> bool:
        current = node.parent
        while current is not None:
            if current.type in self.annotations:
                return True
            if self.function(current) or current.type in self.blocks:
                return False
            current = current.parent
        return False

    def read(self, node: Node) -> bool:
        parent = node.parent
        if parent is None:
            return True
        if self.member_expression(parent):
            receiver, _ = self.member_parts(parent)
            return node == receiver
        if parent.type in self.assignments and field(parent, "left") == node:
            return False
        if parent.type in {"expression_list", "pattern_list"}:
            return self.read(parent)
        if parent.type == "delete_statement":
            return False
        if parent.type in {"keyword_argument", "pair"}:
            return node != field(parent, "name") and node != field(parent, "key")
        return True

    def collection_values(self, name: str) -> bool:
        return name in self.collection_methods

    def implicit_use(self, name: str) -> bool:
        return name in {*self.implicit_receivers(), "_"}

    def stub(self, node: Node, context: TreeContext) -> bool:
        body = field(node, "body")
        return body is None or spelling(body, context.source).strip() == "..."

    def call(self, node: Node) -> Node | None:
        if node.type not in self.calls:
            return None
        return field(node, "function") or field(node, "constructor")

    def discarded(self, node: Node, context: TreeContext) -> bool:
        parent = node.parent
        if parent is None or node.type == "new_expression":
            return False
        if parent.type in {"expression_statement", "unary_expression"}:
            return parent.type == "expression_statement" or spelling(
                parent, context.source
            ).startswith("void ")
        if parent.type == "expression_list":
            parent = parent.parent
        if parent is None:
            return False
        left = field(parent, "left")
        return left is not None and spelling(left, context.source).strip() == "_"

    def has_result(self, symbol: Symbol) -> bool:
        if symbol.annotation is not None:
            text = symbol.annotation_text.strip().lstrip(":").strip()
            return text not in self.no_results
        if symbol.value is None:
            return False
        return bool(self.returned_values(symbol.value))

    def call_result(self, call: Node, symbol: Symbol, results: ResultResolver) -> ResultKind:
        """Retain declaration evidence for languages without call specialization."""
        if self.has_result(symbol):
            return ResultKind.VALUE
        if symbol.annotation is not None:
            text = symbol.annotation_text.strip().lstrip(":").strip()
            return ResultKind.NONE if text in self.no_results else ResultKind.UNRESOLVED
        if symbol.value is None or field(symbol.value, "body") is None:
            return ResultKind.UNRESOLVED
        return ResultKind.NONE

    def callback_result(
        self, node: Node | None, annotation: Node | None, results: ResultResolver
    ) -> ResultKind:
        """Callback inference requires a language-owned contract interpretation."""
        return ResultKind.UNRESOLVED

    def expression_result(self, node: Node, results: ResultResolver) -> ResultKind:
        """Unknown expression syntax never proves an absent result."""
        return ResultKind.UNRESOLVED

    @abstractmethod
    def parameters(self, node: Node) -> tuple[Node, ...]:
        """Return the adapter's explicit parameter bindings."""

    def parameter_slots(
        self, node: Node, context: TreeContext
    ) -> tuple[tuple[ParameterSlot, Node], ...]:
        parameters = field(node, "parameters")
        if parameters is None:
            return ()
        result: list[tuple[ParameterSlot, Node]] = []
        keyword_only = False
        position = 0
        for parameter in self.parameters(node):
            name = spelling(parameter, context.source)
            if name in self.implicit_receivers():
                continue
            root = parameter
            while root.parent is not None and root.parent != parameters:
                root = root.parent
            previous = root.prev_named_sibling
            keyword_only = keyword_only or (
                previous is not None and previous.type == "keyword_separator"
            )
            slot = self._parameter_slot(root, name, position, keyword_only)
            result.append((slot, parameter))
            keyword_only = keyword_only or slot.kind == "variadic"
            position += 1
        return tuple(result)

    def _parameter_slot(
        self, node: Node, name: str, position: int, keyword_only: bool
    ) -> ParameterSlot:
        kinds = {child.type for child in walk(node)}
        if "dictionary_splat_pattern" in kinds:
            return ParameterSlot("keywords")
        if kinds.intersection(self.variadic_patterns):
            return ParameterSlot("variadic")
        if keyword_only:
            return ParameterSlot("keyword", name=name)
        return ParameterSlot("positional", position=position)

    def constructor_name(self, name: str) -> bool:
        return name in self.constructor_names

    def input_container(self, node: Node, parent: Node) -> bool:
        if parent.type == "pair":
            return field(parent, "value") == node
        return parent.type in {"dictionary", "list", "tuple", "parenthesized_expression"}

    def forwarded_assignment(self, node: Node) -> Node | None:
        parent = node.parent
        return (
            field(parent, "left")
            if parent is not None and parent.type == "assignment" and field(parent, "right") == node
            else None
        )

    def typed_construction(self, node: Node) -> bool:
        return node.type == "new_expression"

    def arguments(self, node: Node) -> tuple[Node, ...]:
        arguments = field(node, "arguments")
        return tuple(arguments.named_children) if arguments is not None else ()

    def specialized(self, node: Node, context: TreeContext) -> bool:
        return node.type in {"subscript", "generic_type"} and not self._broad(node, context)

    def _broad(self, node: Node, context: TreeContext) -> bool:
        return any(spelling(child, context.source) in self.broad_types for child in walk(node))

    def outgoing_values(self, node: Node) -> tuple[Node, ...]:
        if node.type not in self.outgoing_wrappers:
            return ()
        value = field(node, "value")
        return (value,) if value is not None else tuple(node.named_children)

    def returned_values(self, node: Node) -> tuple[Node, ...]:
        body = field(node, "body")
        if body is None:
            return ()
        if body.type not in self.blocks:
            return (body,)
        return tuple(
            value
            for statement in self._body_nodes(body)
            if statement.type == "return_statement"
            for value in statement.named_children
        )

    def _body_nodes(self, body: Node) -> tuple[Node, ...]:
        pending = [body]
        result: list[Node] = []
        while pending:
            node = pending.pop()
            result.append(node)
            pending.extend(
                reversed([child for child in node.named_children if not self.function(child)])
            )
        return tuple(result)

    def dictionary(self, node: Node, context: TreeContext) -> bool:
        parent = node.parent
        if parent is not None and parent.type == "typed_parameter":
            if any(child.type == "dictionary_splat_pattern" for child in parent.named_children):
                return True
        text = spelling(node, context.source).replace(" ", "").lstrip(":").strip("\"'()")
        return text in self.dictionary_names or text.startswith(self.dictionary_prefixes)

    def conversion(self, node: Node) -> Node | None:
        parent = node.parent
        while parent is not None and parent.type in {
            "subscript",
            "dictionary_splat",
            "keyword_argument",
        }:
            parent = parent.parent
        if parent is None or parent.type not in {"argument_list", "arguments"}:
            return None
        call = parent.parent
        return self.call(call) if call is not None else None

    def builtin_converter(self, name: str) -> bool:
        return name in self.builtin_converters

    def concrete_result(self, symbol: Symbol, context: TreeContext) -> bool:
        annotation = symbol.annotation
        return (
            annotation is not None
            and symbol.annotation_text.strip().lstrip(":").strip() not in self.no_results
            and not self._broad(annotation, context)
        )

    def result_consumed(self, node: Node) -> bool:
        parent = node.parent
        if parent is not None and parent.type == "expression_list":
            parent = parent.parent
        return parent is not None and parent.type not in {
            "expression_statement",
            "assignment",
            "assignment_expression",
            "assignment_statement",
            "short_var_declaration",
            "variable_declarator",
        }

    def module_names(self, context: TreeContext) -> tuple[str, ...]:
        return (posixpath.splitext(context.source.path)[0],)

    def import_target(self, entry: ImportedName, context: TreeContext) -> str:
        module = entry.module
        if module.startswith("."):
            directory = posixpath.dirname(context.source.path)
            module = posixpath.normpath(posixpath.join(directory, module))
            module = posixpath.splitext(module)[0]
        return module
