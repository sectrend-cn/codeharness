"""Resolve Python output callbacks from the actual instance parameter binding."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import field, walk
from code_harness.semantics.index import SemanticIndex


@dataclass(frozen=True)
class PythonInstanceOutputs:
    """Require direct class ownership without relying on the spelling self."""

    index: SemanticIndex

    def owner(self, callee: Node) -> Node | None:
        receiver, member = self.index.syntax.member_parts(callee)
        if receiver is None or member is None or self.index.context.root.has_error:
            return None
        method = self._method(receiver)
        body = method.parent if method is not None else None
        owner = body.parent if body is not None else None
        if owner is None or not self._declared(body, self.index.text(member)):
            return None
        return owner

    def _method(self, receiver: Node) -> Node | None:
        method = self._instance_parameter(receiver)
        body = method.parent if method is not None else None
        owner = body.parent if body is not None else None
        if body is None or owner is None:
            return None
        return method if owner.type == "class_definition" and body.type == "block" else None

    def _instance_parameter(self, receiver: Node) -> Node | None:
        symbol = self.index.resolve(receiver)
        if symbol is None or symbol.kind != "parameter" or symbol.writes:
            return None
        method = self.index.scopes[symbol.scope].node
        parameters = self.index.syntax.parameters(method)
        if not parameters or parameters[0] != symbol.node:
            return None
        return method if self._positional_receiver(parameters[0], method) else None

    def _positional_receiver(self, parameter: Node, method: Node) -> bool:
        parameters = field(method, "parameters")
        while parameter.parent is not None and parameter.parent != parameters:
            parameter = parameter.parent
        return not any(
            node.type in {"list_splat_pattern", "dictionary_splat_pattern"}
            for node in walk(parameter)
        )

    def _declared(self, body: Node | None, name: str) -> bool:
        if body is None:
            return False
        methods = [node for node in body.named_children if self._named_method(node, name)]
        fields = self._fields(body, name)
        if methods:
            return len(methods) == 1 and not fields and methods[0].type == "function_definition"
        return 0 < len(fields) <= 2 and len({node.type for node in fields}) == len(fields)

    def _named_method(self, node: Node, name: str) -> bool:
        method = field(node, "definition") if node.type == "decorated_definition" else node
        declared = field(method, "name") if method is not None else None
        return declared is not None and self.index.text(declared) == name

    def _fields(self, body: Node, name: str) -> tuple[Node, ...]:
        return tuple(
            target
            for node in walk(body)
            if (target := self._field_assignment(node, body, name)) is not None
        )

    def _field_assignment(self, node: Node, body: Node, name: str) -> Node | None:
        target = field(node, "left") if node.type == "assignment" else None
        if target is None:
            return None
        if node.parent is not None:
            if node.parent.parent == body and self.index.text(target) == name:
                return target
        receiver, member = self.index.syntax.member_parts(target)
        if receiver is None or member is None or self.index.text(member) != name:
            return None
        method = self._method(receiver)
        return target if self._initializer(method, body) else None

    def _initializer(self, method: Node | None, body: Node) -> bool:
        if method is None or method.parent != body:
            return False
        name = field(method, "name")
        return name is not None and self.index.text(name) == "__init__"
