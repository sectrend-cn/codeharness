"""Bounded TypeScript generic substitution from explicit types and callback results."""

from tree_sitter import Node

from code_harness.languages.javascript.semantic_syntax import JavaScriptSemanticSyntax
from code_harness.parsing.treesitter import field, walk
from code_harness.semantics.model import Symbol
from code_harness.semantics.results import ResultKind, ResultResolver


class TypeScriptResultSyntax(JavaScriptSemanticSyntax):
    """Specialize direct type-parameter results without erasing unresolved evidence."""

    def call_result(self, call: Node, symbol: Symbol, results: ResultResolver) -> ResultKind:
        function = symbol.value
        if function is None or symbol.annotation is None:
            return super().call_result(call, symbol, results)
        if self._deferred_result(function):
            return ResultKind.VALUE
        annotation = self._result_type(symbol.annotation)
        parameters = field(function, "type_parameters")
        if annotation.type != "type_identifier" or parameters is None:
            return super().call_result(call, symbol, results)
        return self._specialized_result(call, function, annotation, results)

    def _specialized_result(
        self, call: Node, function: Node, annotation: Node, results: ResultResolver
    ) -> ResultKind:
        parameters = field(function, "type_parameters")
        if parameters is None:
            return ResultKind.UNRESOLVED
        names = tuple(field(parameter, "name") for parameter in parameters.named_children)
        positions = [i for i, name in enumerate(names) if name and name.text == annotation.text]
        if not positions or self._overloaded(function):
            return ResultKind.UNRESOLVED
        explicit = field(call, "type_arguments")
        if explicit is not None and positions[0] < explicit.named_child_count:
            return self._annotated_result(explicit.named_children[positions[0]])
        return self._inferred_result(call, function, annotation, results)

    def _overloaded(self, function: Node) -> bool:
        parent = function.parent
        if parent is not None and parent.type == "export_statement":
            parent = parent.parent
        if parent is None:
            return False
        name = field(function, "name")
        siblings: list[Node] = []
        for sibling in parent.named_children:
            if sibling.type == "export_statement" and sibling.named_child_count == 1:
                sibling = sibling.named_children[0]
            siblings.append(sibling)
        return (
            name is not None
            and sum(
                other.text == name.text
                for sibling in siblings
                if (other := field(sibling, "name")) is not None
            )
            > 1
        )

    def _callback_body_result(self, node: Node | None, results: ResultResolver) -> ResultKind:
        if node is not None and self._overloaded(node):
            return ResultKind.UNRESOLVED
        return super()._callback_body_result(node, results)

    def _inferred_result(
        self, call: Node, function: Node, result: Node, results: ResultResolver
    ) -> ResultKind:
        if not self._simple_parameters(function):
            return ResultKind.UNRESOLVED
        arguments = self.arguments(call)
        evidence: list[ResultKind] = []
        for position, parameter in enumerate(self.parameters(function)):
            annotation = self.parameter_annotation(parameter, function)
            if annotation is None:
                continue
            if not any(node.text == result.text for node in walk(annotation)):
                continue
            if position >= len(arguments):
                return ResultKind.UNRESOLVED
            evidence.append(self._argument_result(annotation, result, arguments[position], results))
        return ResultKind.inferred(tuple(evidence))

    def _argument_result(
        self, annotation: Node, result: Node, argument: Node, results: ResultResolver
    ) -> ResultKind:
        contract = self._result_type(annotation)
        returned = field(contract, "return_type")
        if contract.type == "function_type" and returned is not None:
            if field(contract, "type_parameters") is not None:
                return ResultKind.UNRESOLVED
            if self._result_type(returned).text != result.text:
                return ResultKind.UNRESOLVED
            parameters = field(contract, "parameters")
            if parameters is not None and any(n.text == result.text for n in walk(parameters)):
                return ResultKind.UNRESOLVED
            return results.callback(argument)
        if contract.text == result.text:
            return results.expression(argument)
        return ResultKind.UNRESOLVED
