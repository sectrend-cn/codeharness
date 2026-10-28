"""Go imported serializers, payload results and terminal output APIs."""

from tree_sitter import Node

from code_harness.languages.alias_syntax import GrammarNames
from code_harness.languages.encoding_syntax import GrammarEncoding
from code_harness.languages.go.encoding_members import GoInstanceOutputs
from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames
from code_harness.semantics.index import SemanticIndex


class GoEncodingNames(GrammarNames):
    """A single-expression assignment retains an imported callable's identity."""

    def transparent(self, node: Node) -> Node | None:
        if node.type == "expression_list" and node.named_child_count == 1:
            return node.named_children[0]
        return super().transparent(node)


class GoEncodingSyntax(GrammarEncoding):
    """Track JSON bytes separately from errors and keep imported identities exact."""

    names = GoEncodingNames()
    encoders = frozenset({"encoding/json.Marshal", "encoding/json.MarshalIndent"})
    decoders = frozenset({"encoding/json.Unmarshal"})

    def instance_owner(self, callee: Node, index: SemanticIndex) -> Node | None:
        return GoInstanceOutputs(index).owner(callee)

    def single_result(self, name: str) -> bool:
        return name not in self.encoders

    def result_binding(self, node: Node, names: QualifiedNames) -> Node | None:
        callee = names.index.syntax.call(node)
        if callee is None or names.qualified(callee) not in self.encoders:
            return None
        return self._payload_target(node)

    def _payload_target(self, node: Node) -> Node | None:
        values = node.parent
        if values is None or values.named_children != [node]:
            return None
        statement = values.parent
        if statement is None or statement.type not in {
            "short_var_declaration",
            "assignment_statement",
        }:
            return None
        if values != field(statement, "right"):
            return None
        targets = field(statement, "left")
        if targets is None or len(targets.named_children) != 2:
            return None
        target = targets.named_children[0]
        return target if target.type == "identifier" and target.text != b"_" else None

    def terminal(self, callee: Node, value: Node, names: QualifiedNames) -> bool:
        name = names.qualified(callee)
        slot = self.argument(callee, value)
        if slot is None or slot.kind != "positional":
            return False
        if name in {"fmt.Print", "fmt.Println"}:
            return True
        if name in {"os.Stdout.Write", "os.Stderr.Write"}:
            return slot.position == 0
        return name == "os.WriteFile" and slot.position == 1
