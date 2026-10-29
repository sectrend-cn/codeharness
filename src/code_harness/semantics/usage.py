"""Unused declarations and ignored results from resolved source-local evidence."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import walk
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import Symbol
from code_harness.semantics.options import USAGE_RULES as USAGE_RULES
from code_harness.semantics.results import CallResults, ResultKind


@dataclass(frozen=True)
class UsageRule:
    """Own declaration diagnostics independently of type and metric checks."""

    name: str = "builtin.usage"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements(semantic_evidence=True)
    rule_ids: tuple[str, ...] = USAGE_RULES

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        if context.root.has_error:
            return ()
        index = context.require_index()
        evidence = context.require_usage()
        return self.evaluate(index, evidence.unresolved, evidence.contract_reads)

    def evaluate(
        self,
        index: SemanticIndex,
        unresolved: frozenset[str] = frozenset(),
        contract_reads: frozenset[int] = frozenset(),
    ) -> tuple[Finding, ...]:
        """Evaluate a source after local or project references have been resolved."""
        context = index.context
        uncertain = unresolved.union(index.unresolved_reads)
        findings: list[Finding] = []
        for symbol in index.symbols():
            member = (
                symbol.kind == "field"
                or bool(index.scopes[symbol.scope].owner)
                or symbol.node.id in index.attached_members
            )
            if member and symbol.name in uncertain:
                continue
            if self._unused(symbol, index, contract_reads):
                findings.append(self._finding(symbol.node, symbol.kind, symbol.name, context))
        findings.extend(self._returns(index))
        return tuple(findings)

    def _unused(self, symbol: Symbol, index: SemanticIndex, contract_reads: frozenset[int]) -> bool:
        if self._implicit_use(symbol, index) or symbol.node.id in contract_reads:
            return False
        if symbol.kind == "field" and index.scopes[symbol.scope].externally_used:
            return False
        if symbol.kind == "parameter":
            return not symbol.reads and not self._stub(index.scopes[symbol.scope].node, index)
        if symbol.kind == "function":
            return not self._stub(symbol.value or symbol.node, index) and self._unused_function(
                symbol
            )
        return not symbol.reads

    def _implicit_use(self, symbol: Symbol, index: SemanticIndex) -> bool:
        return (
            symbol.kind not in {"parameter", "function", "field"}
            or symbol.exported
            or symbol.external
            or index.syntax.implicit_use(symbol.name)
        )

    def _stub(self, node: Node, index: SemanticIndex) -> bool:
        return index.syntax.stub(node, index.context)

    def _unused_function(self, symbol: Symbol) -> bool:
        if symbol.value is None:
            return False
        return not any(not self._inside(read, symbol.value) for read in symbol.reads)

    def _inside(self, node: Node, owner: Node) -> bool:
        current: Node | None = node
        while current is not None:
            if current == owner:
                return True
            current = current.parent
        return False

    def _returns(self, index: SemanticIndex) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        results = CallResults(index)
        for node in walk(index.context.root):
            callee = index.syntax.call(node)
            if callee is None or not index.syntax.discarded(node, index.context):
                continue
            symbol = index.resolve(callee) if callee is not None else None
            if symbol is None or symbol.kind != "function":
                continue
            result = results.expression(node)
            if result == ResultKind.VALUE or (
                result == ResultKind.UNRESOLVED and index.syntax.has_result(symbol)
            ):
                findings.append(self._finding(node, "return", symbol.name, index.context))
        return tuple(findings)

    def _finding(self, node: Node, kind: str, name: str, context: TreeContext) -> Finding:
        message = (
            f"{kind.capitalize()} {name!r} has no resolved read usage in the audited snapshots"
        )
        if kind == "return":
            message = f"Return value from {name!r} is discarded"
        return Finding(
            path=context.source.path,
            line=node.start_point.row + 1,
            column=node.start_point.column + 1,
            rule=f"unused.{kind}",
            message=message,
            severity="warning" if kind == "return" else "error",
        )
