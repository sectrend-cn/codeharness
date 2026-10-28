"""Declaration read evidence shared only within resolved inheritance contracts."""

from tree_sitter import Node

from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import ParameterSlot, Scope, Symbol


class OverrideUsage:
    """Connect member overrides and parameter slots through established base classes."""

    def __init__(self, indexes: tuple[SemanticIndex, ...]) -> None:
        self.indexes = indexes
        self.parameters: dict[int, dict[ParameterSlot, Symbol]] = {}
        self.links: dict[int, set[int]] = {}
        self.members: dict[int, Symbol] = {}
        self.owners = tuple(
            (index, scope) for index in indexes for scope in index.scopes if scope.owner
        )
        self.dispatch: dict[tuple[int, str], frozenset[int]] = {}
        for index in indexes:
            for scope in index.scopes:
                self.parameters[scope.node.id] = self._parameters(index, scope)
                self.members.update((symbol.node.id, symbol) for symbol in self._members(scope))

    def used_declarations(self) -> frozenset[int]:
        """Propagate real reads across resolved overrides without fabricating source reads."""
        for index in self.indexes:
            for scope in index.scopes:
                self._connect(index, scope)
        used = self._observed_reads()
        pending = list(used)
        while pending:
            for peer in self.links.get(pending.pop(), set()):
                if peer not in used:
                    used.add(peer)
                    pending.append(peer)
        return frozenset(used)

    def _members(self, scope: Scope) -> tuple[Symbol, ...]:
        return tuple(scope.symbols.values()) if scope.owner else ()

    def _observed_reads(self) -> set[int]:
        used = {
            parameter.node.id
            for slots in self.parameters.values()
            for parameter in slots.values()
            if parameter.reads
        }
        for symbol in self.members.values():
            used.update(self._dispatch_members(symbol))
        return used

    def _parameters(self, index: SemanticIndex, scope: Scope) -> dict[ParameterSlot, Symbol]:
        result: dict[ParameterSlot, Symbol] = {}
        for slot, node in index.syntax.parameter_slots(scope.node, index.context):
            symbol = scope.symbols.get(index.text(node))
            if symbol is not None:
                result[slot] = symbol
        return result

    def _dispatch_scope(self, node: Node) -> Scope | None:
        for index in self.indexes:
            if node.id not in index.locations:
                continue
            receiver, _ = index.syntax.member_parts(node)
            if receiver is None or index.syntax.base_receiver(receiver):
                return None
            return self._dynamic_scope(index, receiver)
        return None

    def _dynamic_scope(self, index: SemanticIndex, receiver: Node) -> Scope | None:
        receiver = index.syntax.single_value(receiver)
        target = index.resolve(receiver)
        if target is not None:
            return target.class_scope if self._dynamic_receiver(index, target) else None
        callee = index.syntax.constructor(receiver)
        target = index.resolve(callee) if callee is not None else None
        return target.class_scope if target is not None and target.kind == "function" else None

    def _dispatch_members(self, symbol: Symbol) -> set[int]:
        used: set[int] = set()
        for read in symbol.reads:
            if self._inside(read, symbol.value):
                continue
            receiver = self._dispatch_scope(read)
            if receiver is not None:
                used.update(self._implementations(receiver, symbol))
        return used

    def _implementations(self, receiver: Scope, symbol: Symbol) -> frozenset[int]:
        key = receiver.node.id, symbol.name
        if key in self.dispatch:
            return self.dispatch[key]
        result: set[int] = set()
        for index, scope in self.owners:
            if not self._inherits(scope, receiver):
                continue
            member = index.member(scope, symbol.name)
            if member is not None and member.kind == symbol.kind:
                result.add(member.node.id)
        self.dispatch[key] = frozenset(result)
        return self.dispatch[key]

    def _inherits(self, scope: Scope, base: Scope) -> bool:
        pending = [scope]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current is base:
                return True
            if current.node.id not in seen:
                seen.add(current.node.id)
                pending.extend(current.bases)
        return False

    def _dynamic_receiver(self, index: SemanticIndex, target: Symbol) -> bool:
        if target.kind == "class":
            return False
        if target.value is None:
            return True
        callee = index.syntax.constructor(index.syntax.single_value(target.value))
        constructor = index.resolve(callee) if callee is not None else None
        return constructor is None or constructor.kind != "class"

    def _inside(self, node: Node, owner: Node | None) -> bool:
        current: Node | None = node
        while current is not None:
            if current == owner:
                return True
            current = current.parent
        return False

    def _connect(self, index: SemanticIndex, scope: Scope) -> None:
        if not scope.owner:
            return
        for member in scope.symbols.values():
            if not self._instance_method(index, member):
                continue
            for base in scope.bases:
                inherited = index.member(base, member.name)
                if inherited is not None and self._instance_method(index, inherited):
                    self._override(member, inherited)

    def _instance_method(self, index: SemanticIndex, member: Symbol) -> bool:
        return (
            member.kind == "function"
            and member.value is not None
            and not index.syntax.constructor_name(member.name)
            and not index.syntax.static_member(member.value)
        )

    def _override(self, member: Symbol, inherited: Symbol) -> None:
        if member.kind == "function" and member.value is not None and inherited.value is not None:
            self._link(member.value.id, inherited.value.id)

    def _link(self, method: int, inherited: int) -> None:
        own = self.parameters.get(method, {})
        parent = self.parameters.get(inherited, {})
        for slot, parameter in own.items():
            counterpart = parent.get(slot)
            if counterpart is not None:
                self.links.setdefault(parameter.node.id, set()).add(counterpart.node.id)
                self.links.setdefault(counterpart.node.id, set()).add(parameter.node.id)
