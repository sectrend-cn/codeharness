"""Resolve constructor-property reads without changing unrelated rule evidence."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.parsing.treesitter import walk
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import Scope, Symbol


class ParameterPropertyIndex(SemanticIndex):
    """Resolve lexical base identities only in the dedicated property evidence graph."""

    def _base_scope(self, node: Node) -> Scope | None:
        symbol = self.resolve(node)
        return symbol.class_scope if symbol is not None else super()._base_scope(node)


@dataclass(frozen=True)
class ParameterPropertyUsage:
    """Connect member reads to canonical parameter declarations by receiver identity."""

    indexes: tuple[SemanticIndex, ...]

    def used_declarations(self) -> frozenset[int]:
        used: set[int] = set()
        for index in self.indexes:
            for node in walk(index.context.root):
                if not index.syntax.member_expression(node) or not index.syntax.read(node):
                    continue
                receiver, name = index.syntax.member_parts(node)
                if receiver is None or name is None:
                    continue
                owner = self._receiver_scope(index, receiver, frozenset())
                symbol = self._property(owner, index.text(name)) if owner is not None else None
                if symbol is not None:
                    used.add(symbol.node.id)
        return frozenset(used)

    def _property(self, scope: Scope, name: str) -> Symbol | None:
        pending = [scope]
        seen: set[int] = set()
        while pending:
            owner = pending.pop()
            if owner.node.id in seen:
                continue
            seen.add(owner.node.id)
            symbol = owner.parameter_properties.get(name)
            if symbol is not None:
                return symbol
            if name in owner.symbols:
                return None
            pending.extend(owner.bases)
        return None

    def _receiver_scope(
        self, index: SemanticIndex, node: Node, seen: frozenset[int]
    ) -> Scope | None:
        if node.id in seen:
            return None
        seen = seen | {node.id}
        narrowed = self._narrowed_scope(index, node)
        if narrowed is not None:
            return narrowed
        scope = index.value_scope(node)
        if scope is not None:
            return scope
        branches = index.syntax.conditional_branches(node)
        if branches:
            return self._conditional_scope(index, branches, seen)
        symbol = index.resolve(node)
        if symbol is not None and symbol.value is not None and len(symbol.writes) == 1:
            return self._receiver_scope(index, symbol.value, seen)
        return None

    def _conditional_scope(
        self, index: SemanticIndex, branches: tuple[Node, ...], seen: frozenset[int]
    ) -> Scope | None:
        owners = tuple(self._receiver_scope(index, branch, seen) for branch in branches)
        first = owners[0]
        return first if first is not None and all(owner is first for owner in owners) else None

    def _narrowed_scope(self, index: SemanticIndex, node: Node) -> Scope | None:
        symbol = index.resolve(node)
        if symbol is None:
            return None
        for binding, declared in index.syntax.narrowed_instances(node):
            if index.resolve(binding) is not symbol:
                continue
            if any(
                binding.end_byte < write.start_byte < node.start_byte for write in symbol.writes
            ):
                continue
            target = index.resolve(declared)
            if target is not None and target.kind == "class":
                return target.class_scope
        return None
