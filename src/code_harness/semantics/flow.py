"""Prove every observed use of a local carrier reaches an accepted destination."""

from dataclasses import dataclass
from typing import Literal, Protocol

from tree_sitter import Node

from code_harness.semantics.index import SemanticIndex

type Destination = Literal["permit", "reject", "follow"]


class Destinations(Protocol):
    """Classify a use without owning traversal or alias propagation."""

    def classify(self, node: Node) -> Destination: ...


@dataclass(frozen=True)
class ValueFlow:
    """Share cycle-safe container and single-assignment forwarding across policies."""

    index: SemanticIndex
    destinations: Destinations

    def permitted(self, node: Node, seen: frozenset[int] = frozenset()) -> bool:
        if node.id in seen:
            return False
        decision = self.destinations.classify(node)
        if decision != "follow":
            return decision == "permit"
        seen = seen | {node.id}
        parent = node.parent
        if parent is None:
            return False
        if self.index.syntax.input_container(node, parent):
            return self.permitted(parent, seen)
        return self._forwarded(node, seen)

    def binding_permitted(self, target: Node, origin: Node) -> bool:
        """Follow a grammar-proven payload result without including sibling results."""
        symbol = self.index.resolve(target)
        return (
            symbol is not None
            and symbol.kind == "variable"
            and symbol.value is not None
            and self.index.syntax.single_value(symbol.value) == origin
            and len(symbol.writes) == 1
            and bool(symbol.reads)
            and all(self.permitted(read, frozenset({origin.id})) for read in symbol.reads)
        )

    def _forwarded(self, node: Node, seen: frozenset[int]) -> bool:
        target = self.index.syntax.forwarded_assignment(node)
        symbol = self.index.resolve(target) if target is not None else None
        return (
            symbol is not None
            and symbol.kind == "variable"
            and symbol.value == node
            and len(symbol.writes) == 1
            and bool(symbol.reads)
            and all(self.permitted(read, seen) for read in symbol.reads)
        )
