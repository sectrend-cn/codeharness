"""Java serializer identities and exact invocation output slots."""

from tree_sitter import Node

from code_harness.languages.alias_syntax import GrammarNames
from code_harness.languages.encoding_syntax import GrammarEncoding
from code_harness.languages.java.encoding_members import JavaInstanceOutputs
from code_harness.languages.java.encoding_types import JavaEncodingTypes
from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames
from code_harness.semantics.index import SemanticIndex


class JavaEncodingSyntax(GrammarEncoding):
    """Recognize imported Gson/Jackson receivers and explicitly configured APIs."""

    names = GrammarNames(frozenset({"System"}))
    encoders = frozenset(
        {
            "com.google.gson.Gson.toJson",
            "com.fasterxml.jackson.databind.ObjectMapper.writeValueAsString",
            "com.fasterxml.jackson.databind.ObjectMapper.writeValueAsBytes",
        }
    )
    decoders = frozenset(
        {
            "com.google.gson.Gson.fromJson",
            "com.fasterxml.jackson.databind.ObjectMapper.readValue",
            "com.fasterxml.jackson.databind.ObjectMapper.readTree",
        }
    )

    def encoder(self, name: str, callee: Node) -> bool:
        if name != "com.google.gson.Gson.toJson":
            return super().encoder(name, callee)
        arguments = field(callee, "arguments")
        return (
            arguments is not None
            and len(
                [
                    child
                    for child in arguments.named_children
                    if child.type not in {"line_comment", "block_comment"}
                ]
            )
            == 1
        )

    def qualified(self, callee: Node, names: QualifiedNames) -> str:
        qualified = names.qualified(callee)
        if qualified:
            return qualified
        receiver, member = names.index.syntax.member_parts(callee)
        if receiver is None or member is None:
            return ""
        owner = JavaEncodingTypes(names).receiver(receiver)
        return f"{owner}.{names.index.text(member)}" if owner else ""

    def instance_owner(self, callee: Node, index: SemanticIndex) -> Node | None:
        return JavaInstanceOutputs(index).owner(callee)

    def instance_member(self, callee: Node, index: SemanticIndex) -> Node | None:
        return JavaInstanceOutputs(index).member(callee)

    def invocation(self, callee: Node) -> Node | None:
        return callee if callee.type == "method_invocation" else callee.parent

    def terminal(self, callee: Node, value: Node, names: QualifiedNames) -> bool:
        name = self.qualified(callee, names).removeprefix("java.lang.")
        slot = self.argument(callee, value)
        if slot is None or slot.kind != "positional" or slot.position != 0:
            return False
        return name in {
            "System.out.print",
            "System.out.println",
            "System.err.print",
            "System.err.println",
        }
