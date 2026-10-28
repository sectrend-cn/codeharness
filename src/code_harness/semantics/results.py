"""Call-specific result evidence over the session's immutable source snapshots."""

from enum import Enum
from typing import TYPE_CHECKING, Protocol

from tree_sitter import Node

if TYPE_CHECKING:
    from code_harness.semantics.index import SemanticIndex


class ResultKind(Enum):
    """Keep unavailable inference distinct from a proven absence of a result."""

    NONE = "no_result"
    VALUE = "value_result"
    UNRESOLVED = "unresolved"

    @classmethod
    def inferred(cls, evidence: tuple["ResultKind", ...]) -> "ResultKind":
        """Require every inference input before proving an absent generic result."""
        if not evidence or cls.UNRESOLVED in evidence:
            return cls.UNRESOLVED
        return cls.VALUE if cls.VALUE in evidence else cls.NONE


class ResultResolver(Protocol):
    """Resolve expressions and callback contracts in their owning snapshots."""

    def expression(self, node: Node) -> ResultKind: ...
    def callback(self, node: Node) -> ResultKind: ...
    def index_for(self, node: Node) -> "SemanticIndex": ...


class CallResults:
    """Own recursion guards and declaration ownership for one result query."""

    def __init__(self, index: "SemanticIndex") -> None:
        self.index = index
        self.active: set[int] = set()

    def index_for(self, node: Node) -> "SemanticIndex":
        """Locate the immutable declaration snapshot, including imported callbacks."""
        root = node
        while root.parent is not None:
            root = root.parent
        return self.index.snapshot_indexes[root.id]

    def expression(self, node: Node) -> ResultKind:
        if node.id in self.active:
            return ResultKind.UNRESOLVED
        self.active.add(node.id)
        try:
            index = self.index_for(node)
            callee = index.syntax.call(node)
            if callee is None:
                return index.syntax.expression_result(node, self)
            symbol = index.resolve(callee)
            if symbol is None or symbol.kind != "function":
                return ResultKind.UNRESOLVED
            owner = self.index_for(symbol.node)
            return owner.syntax.call_result(node, symbol, self)
        finally:
            self.active.remove(node.id)

    def callback(self, node: Node) -> ResultKind:
        if node.id in self.active:
            return ResultKind.UNRESOLVED
        self.active.add(node.id)
        try:
            return self._callback(node)
        finally:
            self.active.remove(node.id)

    def _callback(self, node: Node) -> ResultKind:
        index = self.index_for(node)
        if index.syntax.function(node):
            return index.syntax.callback_result(node, None, self)
        symbol = index.resolve(node)
        if symbol is None or len(symbol.writes) > 1:
            return ResultKind.UNRESOLVED
        if symbol.kind == "function" and any(write != symbol.node for write in symbol.writes):
            return ResultKind.UNRESOLVED
        owner = self.index_for(symbol.node)
        annotation = symbol.annotation if symbol.kind != "function" else None
        return owner.syntax.callback_result(symbol.value, annotation, self)
