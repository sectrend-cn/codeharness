"""JavaScript and TypeScript JSON and output API interpretation."""

from tree_sitter import Node

from code_harness.languages.alias_syntax import GrammarNames
from code_harness.languages.encoding_syntax import GrammarEncoding
from code_harness.languages.javascript.encoding_members import JavaScriptInstanceOutputs
from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames
from code_harness.semantics.index import SemanticIndex


class JavaScriptEncodingSyntax(GrammarEncoding):
    """Recognize native JSON and terminal or imported filesystem destinations."""

    names = GrammarNames(frozenset({"JSON", "console", "process"}))
    encoders = frozenset({"JSON.stringify"})
    decoders = frozenset({"JSON.parse"})
    terminal_names = frozenset(
        {
            "console.log",
            "console.info",
            "console.warn",
            "console.error",
            "console.debug",
            "process.stdout.write",
            "process.stderr.write",
            "node:process.stdout.write",
            "node:process.stderr.write",
        }
    )
    file_names = frozenset(
        {
            "fs.writeFile",
            "fs.writeFileSync",
            "fs.appendFile",
            "fs.appendFileSync",
            "node:fs.writeFile",
            "node:fs.writeFileSync",
            "node:fs.appendFile",
            "node:fs.appendFileSync",
            "fs/promises.writeFile",
            "fs/promises.appendFile",
            "node:fs/promises.writeFile",
            "node:fs/promises.appendFile",
        }
    )

    def instance_owner(self, callee: Node, index: SemanticIndex) -> Node | None:
        return JavaScriptInstanceOutputs(index).owner(callee)

    def terminal(self, callee: Node, value: Node, names: QualifiedNames) -> bool:
        name = names.qualified(callee)
        if name in self.terminal_names:
            return True
        if name not in self.file_names:
            return False
        call = callee.parent
        arguments = field(call, "arguments") if call is not None else None
        if arguments is None or arguments.named_child_count < 2:
            return False
        payload = arguments.named_children[1]
        return payload.start_byte <= value.start_byte and value.end_byte <= payload.end_byte
