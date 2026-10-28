"""Directional evidence for configured third-party inputs and typed ingress."""

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import walk
from code_harness.semantics.flow import Destination, ValueFlow
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import Symbol
from code_harness.semantics.options import BOUNDARY


class BoundaryEvidence:
    """Track external destinations, registered callbacks and boundary-only carriers."""

    def __init__(self, index: SemanticIndex) -> None:
        self.index = index
        self.calls: set[int] = set()
        self.callbacks: set[int] = set()
        self.typed_calls: set[int] = set()
        self.outbound: set[int] = set()
        self.exemptions: list[Node] = []
        self.findings: list[Finding] = []
        self._external_calls()
        self._callback_returns()
        self._carriers()
        self._incoming()

    def contains(self, node: Node) -> bool:
        return any(
            n.start_byte <= node.start_byte and node.end_byte <= n.end_byte for n in self.exemptions
        )

    def is_library_input(self, node: Node, seen: frozenset[int] = frozenset()) -> bool:
        """Follow inline values and single-assignment locals only to library inputs.

        Internal consumers, retained fields and ordinary function returns cannot
        acquire an exemption from another use at an external call site.
        """
        return ValueFlow(self.index, self).permitted(node, seen)

    def classify(self, node: Node) -> Destination:
        """Recognize only proven library inputs; traversal belongs to ValueFlow."""
        return "permit" if node.id in self.outbound else "follow"

    def _library(self, node: Node) -> bool:
        symbol = self.index.resolve(node)
        if symbol is not None:
            return symbol.kind == "import" and symbol.library
        receiver, _ = self.index.syntax.member_parts(node)
        return receiver is not None and self._library(receiver)

    def _external_calls(self) -> None:
        for node in walk(self.index.context.root):
            callee = self.index.syntax.call(node)
            if callee is None or not self._library(callee):
                continue
            if self.index.in_annotation(node):
                continue
            self.calls.add(node.id)
            if self.index.syntax.typed_construction(node) or self.index.syntax.specialized(
                callee, self.index.context
            ):
                self.typed_calls.add(node.id)
            for argument in self.index.syntax.arguments(node):
                self._outgoing(argument)

    def _outgoing(self, node: Node) -> None:
        self.outbound.add(node.id)
        owner = self.index.value_scope(node)
        if owner is not None:
            owner.externally_used = True
        symbol = self.index.resolve(node)
        if symbol is not None:
            symbol.external = True
            if symbol.kind == "function" and symbol.value is not None:
                self.callbacks.add(symbol.value.id)
        if self.index.syntax.function(node):
            self.callbacks.add(node.id)
        else:
            for child in self.index.syntax.outgoing_values(node):
                self._outgoing(child)

    def _callback_returns(self) -> None:
        for scope in self.index.scopes:
            if scope.node.id in self.callbacks:
                self._callback(scope.node)

    def _callback(self, node: Node) -> None:
        symbol = self.index.functions.get(node.id)
        if symbol is not None and any(read.id not in self.outbound for read in symbol.reads):
            return
        result = self.index.syntax.result_annotation(node)
        if result is not None and self.index.syntax.dictionary(result, self.index.context):
            self.exemptions.append(result)
        self._outgoing_returns(node)

    def _outgoing_returns(self, node: Node) -> None:
        for value in self.index.syntax.returned_values(node):
            self._outgoing(value)

    def _carriers(self) -> None:
        for symbol in self.index.symbols():
            annotation = symbol.annotation
            if annotation is not None and self.index.syntax.dictionary(
                annotation, self.index.context
            ):
                self._carrier(symbol, annotation)

    def _carrier(self, symbol: Symbol, annotation: Node) -> None:
        callback = self.index.scopes[symbol.scope].node.id in self.callbacks
        if symbol.kind == "parameter" and callback:
            if symbol.reads and all(self._converted(read) for read in symbol.reads):
                self.exemptions.append(annotation)
            else:
                self._issue(symbol.node, "Convert callback input into a typed object at ingress")
        elif symbol.kind in {"variable", "parameter"} and symbol.reads:
            if all(read.id in self.outbound for read in symbol.reads):
                self.exemptions.append(annotation)

    def _converted(self, node: Node) -> bool:
        callee = self.index.syntax.conversion(node)
        return callee is not None and self._typed_converter(callee)

    def _typed_converter(self, callee: Node) -> bool:
        target = self.index.resolve(callee)
        if target is None:
            return self.index.syntax.builtin_converter(self.index.text(callee))
        if target.kind == "class":
            return True
        if target.kind == "function" and target.annotation is not None:
            return self.index.syntax.concrete_result(target, self.index.context)
        return False

    def _incoming(self) -> None:
        for node in walk(self.index.context.root):
            if node.id in self.calls.difference(self.typed_calls) and self._unconverted_result(
                node
            ):
                self._issue(
                    node, "Convert the third-party result into a typed object before returning it"
                )
        for symbol in self.index.symbols():
            if self._raw_result(symbol):
                self._issue(
                    symbol.node, "Convert the third-party result into a typed object at ingress"
                )

    def _unconverted_result(self, node: Node) -> bool:
        return self.index.syntax.result_consumed(node) and not self._converted(node)

    def _raw_result(self, symbol: Symbol) -> bool:
        if symbol.kind == "field" and self.index.scopes[symbol.scope].externally_used:
            return False
        value = symbol.value
        if value is not None:
            value = self.index.syntax.single_value(value)
        if (
            value is None
            or value.id not in self.calls.difference(self.typed_calls)
            or not symbol.reads
        ):
            return False
        return not all(self._converted(read) for read in symbol.reads)

    def _issue(self, node: Node, message: str) -> None:
        self.findings.append(
            Finding(
                path=self.index.context.source.path,
                line=node.start_point.row + 1,
                column=node.start_point.column + 1,
                rule=BOUNDARY.name,
                message=message,
            )
        )


class BoundaryRule:
    """Own typed-ingress checks for every registered semantic grammar strategy."""

    name = "builtin.boundaries"
    api_version = 2
    requirements = RuleRequirements(semantic_evidence=True)
    rule_ids = (BOUNDARY.name,)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        if not context.policy.third_party_modules or context.root.has_error:
            return ()
        return tuple(context.require_boundary().findings)
