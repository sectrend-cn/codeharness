"""Python generic callback results retain None, values and unresolved contracts."""

from tree_sitter import Node

from code_harness.languages.python.qualified_names import PythonNameSyntax
from code_harness.languages.semantic_nodes import SemanticNodes
from code_harness.parsing.treesitter import field, walk
from code_harness.semantics.aliases import QualifiedNames
from code_harness.semantics.model import Symbol
from code_harness.semantics.results import ResultKind, ResultResolver


class PythonResultSyntax(SemanticNodes):
    """Interpret direct TypeVar and PEP 695 callback-result relationships."""

    def call_result(self, call: Node, symbol: Symbol, results: ResultResolver) -> ResultKind:
        function = symbol.value
        if function is None:
            return super().call_result(call, symbol, results)
        if self._deferred_result(function):
            return ResultKind.VALUE
        annotation = symbol.annotation
        if annotation is None or not self._type_variable(annotation, function, results):
            return super().call_result(call, symbol, results)
        return self._inferred_result(call, function, self._result_type(annotation), results)

    def _inferred_result(
        self, call: Node, function: Node, result: Node, results: ResultResolver
    ) -> ResultKind:
        arguments = self.arguments(call)
        evidence: list[ResultKind] = []
        parameters = tuple(
            parameter
            for parameter in self.parameters(function)
            if parameter.text not in {b"self", b"cls"}
        )
        for position, parameter in enumerate(parameters):
            declared = self.parameter_annotation(parameter, function)
            if declared is None or not any(n.text == result.text for n in walk(declared)):
                continue
            if position >= len(arguments) or arguments[position].type == "keyword_argument":
                return ResultKind.UNRESOLVED
            evidence.append(self._argument_result(declared, result, arguments[position], results))
        return ResultKind.inferred(tuple(evidence))

    def _argument_result(
        self, declared: Node, result: Node, argument: Node, results: ResultResolver
    ) -> ResultKind:
        returned = self._callable_return(declared, results)
        if returned is None or self._result_type(returned).text != result.text:
            return ResultKind.UNRESOLVED
        contract = self._result_type(declared)
        parameters = contract.named_children[1].named_children[0]
        if any(node.text == result.text for node in walk(parameters)):
            return ResultKind.UNRESOLVED
        return results.callback(argument)

    def _type_variable(self, node: Node, function: Node, results: ResultResolver) -> bool:
        node = self._result_type(node)
        if node.type != "identifier":
            return False
        parameters = field(function, "type_parameters")
        if parameters is not None and any(child.text == node.text for child in walk(parameters)):
            return True
        index = results.index_for(node)
        symbol = index.resolve(node)
        if symbol is None or symbol.value is None or len(symbol.writes) != 1:
            return False
        callee = self.call(symbol.value)
        names = QualifiedNames(index, PythonNameSyntax())
        return callee is not None and names.qualified(callee) in {
            "typing.TypeVar",
            "typing_extensions.TypeVar",
        }

    def _callable_return(self, annotation: Node, results: ResultResolver) -> Node | None:
        node = self._result_type(annotation)
        if node.type != "generic_type" or node.named_child_count != 2:
            return None
        name, arguments = node.named_children
        qualified = QualifiedNames(results.index_for(name), PythonNameSyntax()).qualified(name)
        if qualified not in {"typing.Callable", "collections.abc.Callable"}:
            return None
        return arguments.named_children[-1] if arguments.named_child_count == 2 else None

    def callback_result(
        self, node: Node | None, annotation: Node | None, results: ResultResolver
    ) -> ResultKind:
        if annotation is not None:
            declared = self._callable_return(annotation, results)
            return self._annotated_result(declared)
        if node is None or not self.function(node):
            return ResultKind.UNRESOLVED
        if self._deferred_result(node):
            return ResultKind.VALUE
        declared = self.result_annotation(node)
        if declared is not None:
            return self._annotated_result(declared)
        if field(node, "body") is None:
            return ResultKind.UNRESOLVED
        evidence = tuple(results.expression(value) for value in self.returned_values(node))
        if ResultKind.VALUE in evidence:
            return ResultKind.VALUE
        return ResultKind.UNRESOLVED if ResultKind.UNRESOLVED in evidence else ResultKind.NONE

    def _deferred_result(self, node: Node) -> bool:
        return any(child.type == "async" for child in node.children) or any(
            child.type == "yield" for child in self._body_nodes(field(node, "body") or node)
        )

    def _result_type(self, node: Node) -> Node:
        while node.type == "type" and node.named_child_count == 1:
            node = node.named_children[0]
        return node

    def _annotated_result(self, node: Node | None) -> ResultKind:
        if node is None:
            return ResultKind.UNRESOLVED
        node = self._result_type(node)
        if node.type == "none":
            return ResultKind.NONE
        if node.text in {b"Any", b"object"}:
            return ResultKind.UNRESOLVED
        return ResultKind.VALUE

    def expression_result(self, node: Node, results: ResultResolver) -> ResultKind:
        if node.type == "none":
            return ResultKind.NONE
        if node.type == "parenthesized_expression" and node.named_child_count == 1:
            return results.expression(node.named_children[0])
        if node.type in {
            "integer",
            "float",
            "string",
            "concatenated_string",
            "dictionary",
            "list",
            "tuple",
            "set",
            "true",
            "false",
            "binary_operator",
            "lambda",
        }:
            return ResultKind.VALUE
        return ResultKind.UNRESOLVED
