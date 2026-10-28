"""Prove Python output destinations without exempting arbitrary write-like methods."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import field
from code_harness.semantics.aliases import QualifiedNames


@dataclass(frozen=True)
class PythonOutputs:
    """Identify concrete Python output APIs without owning carrier traversal."""

    names: QualifiedNames

    def terminal(self, callee: Node, value: Node) -> bool:
        name = self.names.qualified(callee)
        if name in {"print", "builtins.print"}:
            return self._print_destination(callee)
        if name in {"sys.stdout.write", "sys.stderr.write"}:
            return True
        receiver, member = field(callee, "object"), field(callee, "attribute")
        if receiver is None or member is None:
            return False
        method = self.names.index.text(member)
        if method == "write_text":
            return self._path(receiver)
        return method == "write" and self._opened_file(receiver, value)

    def _print_destination(self, callee: Node) -> bool:
        call = callee.parent
        if call is None:
            return False
        arguments = field(call, "arguments")
        if arguments is None:
            return False
        for argument in arguments.named_children:
            name = field(argument, "name") if argument.type == "keyword_argument" else None
            if name is not None and self.names.index.text(name) == "file":
                value = field(argument, "value")
                return value is not None and (
                    self.names.qualified(value) in {"sys.stdout", "sys.stderr"}
                    or self._opened_file(value, call)
                )
        return True

    def _path(self, node: Node) -> bool:
        value = self.names.value(node)
        callee = self.names.index.syntax.call(value) if value is not None else None
        return callee is not None and self.names.qualified(callee) == "pathlib.Path"

    def _opened_file(self, receiver: Node, location: Node) -> bool:
        """Recognize writable open context bindings, excluding memory buffers and shadows."""
        parent = location.parent
        while parent is not None:
            if parent.type == "with_statement":
                binding = self._with_binding(parent, receiver)
                if binding is not None:
                    return binding
            if parent.type in {"function_definition", "lambda", "class_definition"}:
                return False
            parent = parent.parent
        return False

    def _with_binding(self, node: Node, receiver: Node) -> bool | None:
        clause = next((child for child in node.named_children if child.type == "with_clause"), None)
        if clause is None:
            return None
        symbol = self.names.index.resolve(receiver)
        if symbol is not None:
            return False
        expression = self._binding_expression(clause, receiver)
        return self._writable_open(expression) if expression is not None else None

    def _binding_expression(self, clause: Node, receiver: Node) -> Node | None:
        for item in clause.named_children:
            pattern = field(item, "value")
            alias = field(pattern, "alias") if pattern is not None else None
            if pattern is None or alias is None:
                continue
            if self.names.index.text(alias) == self.names.index.text(receiver):
                return pattern.named_children[0]
        return None

    def _writable_open(self, node: Node) -> bool:
        callee = field(node, "function") if node.type == "call" else None
        arguments = field(node, "arguments")
        if callee is None or arguments is None:
            return False
        if self.names.qualified(callee) not in {"open", "builtins.open", "io.open"}:
            return False
        mode = self._mode(arguments)
        if mode is None or mode.type != "string":
            return False
        text = self.names.index.text(mode).strip("\"'")
        return bool(set(text).intersection("wax+")) and "b" not in text

    def _mode(self, arguments: Node) -> Node | None:
        positional = [
            child for child in arguments.named_children if child.type != "keyword_argument"
        ]
        mode = positional[1] if len(positional) > 1 else None
        for argument in arguments.named_children:
            name = field(argument, "name") if argument.type == "keyword_argument" else None
            if name is not None and self.names.index.text(name) == "mode":
                mode = field(argument, "value")
        return mode
