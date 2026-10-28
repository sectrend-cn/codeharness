"""Interpret call consumers and serializer identities in tree-sitter grammars."""

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import ParameterSlot


class GrammarEncoding:
    """Preserve argument identity across keyword and parenthesized expressions."""

    encoders = frozenset[str]()
    decoders = frozenset[str]()
    argument_wrappers = frozenset({"keyword_argument", "parenthesized_expression"})
    argument_lists = frozenset({"argument_list", "arguments"})

    def instance_owner(self, callee: Node, index: SemanticIndex) -> Node | None:
        """Unsupported grammars cannot establish an instance output owner."""
        return None

    def instance_member(self, callee: Node, index: SemanticIndex) -> Node | None:
        return index.syntax.member_parts(callee)[1]

    def qualified(self, callee: Node, names: QualifiedNames) -> str:
        return names.qualified(callee)

    def result_binding(self, node: Node, names: QualifiedNames) -> Node | None:
        """Single-result encoders use the ordinary value-flow entry point."""
        return None

    def single_result(self, name: str) -> bool:
        return True

    def encoder(self, name: str, callee: Node) -> bool:
        return name in self.encoders

    def decoder(self, name: str) -> bool:
        return name in self.decoders

    def consumer(self, node: Node, index: SemanticIndex) -> Node | None:
        parent = node.parent
        while parent is not None and parent.type in self.argument_wrappers:
            parent = parent.parent
        if parent is None or parent.type not in self.argument_lists or parent.parent is None:
            return None
        return index.syntax.call(parent.parent)

    def argument(self, callee: Node, value: Node) -> ParameterSlot | None:
        """Locate a payload without guessing positional offsets after a splat."""
        call = self.invocation(callee)
        arguments = field(call, "arguments") if call is not None else None
        if arguments is None:
            return None
        argument = next(
            (child for child in arguments.named_children if self._contains(child, value)), None
        )
        if argument is None:
            return None
        if argument.type == "keyword_argument":
            return self._keyword(argument, value)
        return self._position(arguments, argument)

    def invocation(self, callee: Node) -> Node | None:
        return callee.parent

    def _position(self, arguments: Node, selected: Node) -> ParameterSlot | None:
        position = 0
        for argument in arguments.named_children:
            if argument.type in {
                "list_splat",
                "dictionary_splat",
                "spread_element",
                "variadic_argument",
            }:
                return None
            if argument == selected:
                return ParameterSlot("positional", position)
            if argument.type not in {"keyword_argument", "comment"}:
                position += 1
        return None

    def _keyword(self, argument: Node, value: Node) -> ParameterSlot | None:
        payload, name = field(argument, "value"), field(argument, "name")
        if payload is None or name is None or name.text is None:
            return None
        if not self._contains(payload, value):
            return None
        return ParameterSlot("keyword", name=name.text.decode("utf-8"))

    def _contains(self, container: Node, value: Node) -> bool:
        return container.start_byte <= value.start_byte and value.end_byte <= container.end_byte
