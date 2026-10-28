"""Binding-based evidence for single guarded writes, without whole-program inference."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import Symbol
from code_harness.semantics.projection.contracts import (
    FieldKey,
    Guard,
    ProjectionSyntax,
    Property,
    Write,
)


@dataclass(frozen=True)
class Receiver:
    """Identify a lexical binding and its static member path independently of spelling."""

    binding: int
    members: tuple[FieldKey, ...] = ()


@dataclass(frozen=True)
class Projection:
    """One proven candidate with evidence retained for cluster diagnostics."""

    node: Node
    source: Receiver
    destination: Receiver
    field: FieldKey
    source_name: str
    destination_name: str
    predicate: str


class ProjectionMatcher:
    """Match the same field or an established literal using lexical binding evidence."""

    def __init__(self, index: SemanticIndex, syntax: ProjectionSyntax) -> None:
        self.index = index
        self.syntax = syntax

    def receiver(self, node: Node, seen: frozenset[int] = frozenset()) -> Receiver | None:
        node = self.syntax.unwrap(node)
        if node.id in seen:
            return None
        seen = seen | {node.id}
        member = self.syntax.property(node, self.index)
        if member is not None:
            base = self.receiver(member.receiver, seen)
            return Receiver(base.binding, (*base.members, member.key)) if base else None
        if not self.index.syntax.reference(node):
            return None
        symbol = self.index.resolve(node)
        if symbol is None:
            return None
        return self._binding(node, symbol, seen)

    def _binding(self, node: Node, symbol: Symbol, seen: frozenset[int]) -> Receiver | None:
        value = symbol.value
        if value is not None and self.syntax.immutable_alias(symbol.node):
            if len(symbol.writes) != 1 or value.end_byte >= node.start_byte:
                return None
            value = self.syntax.unwrap(value)
            if self.index.syntax.identifier(value):
                target = self.index.resolve(value)
                if target is None or not self._stable(target):
                    return None
                return self.receiver(value, seen)
        return Receiver(symbol.node.id)

    def _stable(self, symbol: Symbol) -> bool:
        return len(symbol.writes) <= (0 if symbol.kind == "parameter" else 1)

    def candidate(self, node: Node, region: Node) -> Projection | None:
        branches = self.syntax.branches(node)
        if branches is None or node.has_error:
            return None
        guard = self.syntax.guard(branches.condition, self.index)
        if guard is None:
            return None
        action = branches.consequence if guard.when else branches.alternative
        other = branches.alternative if guard.when else branches.consequence
        if action is None or not self.syntax.empty(other):
            return None
        write = self.syntax.write(action, self.syntax.construction(region), self.index)
        if write is None or not self._value(guard, write.value):
            return None
        return self._projection(node, region, guard, write)

    def _value(self, guard: Guard, node: Node) -> bool:
        member = self.syntax.property(node, self.index)
        if member is not None:
            return self._same_property(guard.source, member)
        literal = self.syntax.primitive(node, self.index)
        return guard.literal.kind in {"boolean", "number", "string"} and literal == guard.literal

    def _same_property(self, left: Property, right: Property) -> bool:
        receiver = self.receiver(left.receiver)
        return (
            receiver is not None
            and receiver == self.receiver(right.receiver)
            and left.key == right.key
        )

    def _projection(
        self, node: Node, region: Node, guard: Guard, write: Write
    ) -> Projection | None:
        source = self.receiver(guard.source.receiver)
        destination = self.receiver(write.receiver) if write.receiver else Receiver(region.id)
        if source is None or destination is None:
            return None
        destination_name = (
            self.index.text(write.receiver)
            if write.receiver is not None
            else self.syntax.destination(region, self.index)
        )
        return Projection(
            node,
            source,
            destination,
            write.key,
            self.index.text(guard.source.receiver),
            destination_name,
            guard.description,
        )
