"""Resolve lexical reads and member ownership without widening syntax contracts."""

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.parsing.treesitter import spelling, walk
from code_harness.semantics.model import Scope, SemanticSyntax, Symbol, SymbolKind


class SemanticIndex:
    """Own one snapshot's scopes, declarations, resolved reads and external uses."""

    def __init__(self, context: TreeContext, syntax: SemanticSyntax) -> None:
        self.context = context
        self.syntax = syntax
        self.snapshot_indexes: dict[int, SemanticIndex] = {context.root.id: self}
        self.scopes = [Scope(context.root, None)]
        self.locations: dict[int, int] = {}
        self.declarations: set[int] = set()
        self.classes: dict[str, int] = {}
        self.functions: dict[int, Symbol] = {}
        self.imported_classes: dict[str, Scope] = {}
        self.peer_symbols: dict[str, Symbol] = {}
        self.unresolved_reads: set[str] = set()
        self.attached_members: set[int] = set()
        self._declare(context.root, 0)
        self._imports()
        self._receivers()
        self._inheritance()
        self._assignments()
        self._iterations()
        self._reads()

    def text(self, node: Node) -> str:
        return spelling(node, self.context.source)

    def symbols(self) -> tuple[Symbol, ...]:
        declarations = {
            symbol.node.id: symbol
            for scope in self.scopes
            for symbol in (*scope.symbols.values(), *scope.static_symbols.values())
        }
        return tuple(declarations.values())

    def lookup(self, name: str, scope: int) -> Symbol | None:
        current: int | None = scope
        while current is not None:
            frame = self.scopes[current]
            symbol = frame.symbols.get(name) or frame.static_symbols.get(name)
            if symbol is not None:
                return symbol
            current = frame.parent
        return self.peer_symbols.get(name)

    def resolve(self, node: Node) -> Symbol | None:
        if self.syntax.reference(node):
            symbol = self.lookup(self.text(node), self.locations.get(node.id, 0))
            seen: set[int] = set()
            while symbol is not None and symbol.target is not None and symbol.node.id not in seen:
                seen.add(symbol.node.id)
                symbol = symbol.target
            return symbol
        if self.syntax.member_expression(node):
            return self._member(node)
        child = self.syntax.wrapped_value(node)
        return self.resolve(child) if child is not None else None

    def _bind(self, name: Node, kind: SymbolKind, scope: int, static: bool = False) -> Symbol:
        symbol = Symbol(self.text(name), name, kind, scope)
        frame = self.scopes[scope]
        separate = static and bool(frame.owner) and not self.syntax.shared_member_namespace()
        declarations = frame.static_symbols if separate else frame.symbols
        declarations[symbol.name] = symbol
        self.declarations.add(name.id)
        return symbol

    def _declare(self, node: Node, scope: int) -> None:
        self.locations[node.id] = scope
        if self.syntax.class_name(node) is not None:
            scope = self._class(node, scope)
        elif self.syntax.function(node):
            scope = self._function(node, scope)
        elif self.syntax.block_scope(node):
            self.scopes.append(Scope(node, scope))
            scope = len(self.scopes) - 1
        for child in node.named_children:
            self._declare(child, scope)
        self._fields(node, scope)

    def _fields(self, node: Node, scope: int) -> None:
        for name in self.syntax.field_names(node):
            symbol = self._bind(name, "field", scope)
            symbol.annotation = self.syntax.annotation(node)
            symbol.value = self.syntax.value(node)

    def _class(self, node: Node, scope: int) -> int:
        name = self.syntax.class_name(node)
        if name is None:
            return scope
        symbol = self._bind(name, "class", scope)
        symbol.type_name = symbol.name
        self.classes[symbol.name] = len(self.scopes)
        self.scopes.append(Scope(node, scope, owner=symbol.name))
        symbol.class_scope = self.scopes[-1]
        return len(self.scopes) - 1

    def _function(self, node: Node, scope: int) -> int:
        name = self.syntax.function_name(node)
        if name is not None:
            symbol = self._bind(name, "function", scope, self.syntax.static_member(node))
            symbol.value = node
            symbol.annotation = self.syntax.result_annotation(node)
            symbol.annotation_text = (
                self.text(symbol.annotation) if symbol.annotation is not None else ""
            )
            symbol.exported = self.syntax.exported(node, symbol.name, self.context)
            self.functions[node.id] = symbol
        self.scopes.append(Scope(node, scope))
        own = len(self.scopes) - 1
        for parameter in self.syntax.parameters(node):
            symbol = self._bind(parameter, "parameter", own)
            symbol.annotation = self.syntax.parameter_annotation(parameter, node)
            if self.scopes[scope].owner and self.syntax.parameter_property(
                parameter, node, self.context
            ):
                self.scopes[scope].parameter_properties[symbol.name] = symbol
        return own

    def _imports(self) -> None:
        configured = self.context.policy.third_party_modules
        for entry in self.syntax.imports(self.context):
            scope = self.locations.get(entry.node.id, 0)
            existing = self.scopes[scope].symbols.get(entry.name)
            if existing is not None and existing.node.start_byte > entry.node.start_byte:
                continue
            symbol = self._bind(entry.node, "variable", scope)
            self.scopes[scope].symbols.pop(symbol.name)
            symbol.name = entry.name
            symbol.kind = "import"
            symbol.library = entry.module in configured
            self.scopes[scope].symbols[symbol.name] = symbol

    def _receivers(self) -> None:
        for scope_id, scope in enumerate(self.scopes):
            self._implicit_receiver(scope_id, scope)
            self._explicit_receivers(scope_id, scope)
            for symbol in (*scope.symbols.values(), *scope.static_symbols.values()):
                symbol.type_name = symbol.type_name or self._declared_type(symbol.annotation)
                symbol.class_scope = symbol.class_scope or self._annotation_scope(symbol.annotation)

    def _implicit_receiver(self, scope_id: int, scope: Scope) -> None:
        parent = self.scopes[scope.parent] if scope.parent is not None else None
        if parent is None or not parent.owner:
            return
        for name in self.syntax.implicit_receivers():
            symbol = scope.symbols.get(name)
            if symbol is None:
                symbol = Symbol(name, scope.node, "variable", scope_id)
                scope.symbols[name] = symbol
            symbol.type_name = parent.owner
            symbol.class_scope = parent

    def _explicit_receivers(self, scope_id: int, scope: Scope) -> None:
        for name, annotation in self.syntax.receivers(scope.node):
            symbol = scope.symbols.get(self.text(name)) or self._bind(name, "variable", scope_id)
            symbol.annotation = annotation
            owner = self.class_scope(self._declared_type(symbol.annotation))
            method = self.functions.get(scope.node.id)
            if owner is not None and method is not None:
                owner.symbols[method.name] = method
                self.attached_members.add(method.node.id)

    def _annotation_scope(self, node: Node | None) -> Scope | None:
        if node is None:
            return None
        node = self.syntax.element_type(node) or node
        for child in walk(node):
            symbol = self.resolve(child)
            if symbol is not None and symbol.kind == "class":
                return symbol.class_scope
        return self.class_scope(self._declared_type(node))

    def _declared_type(self, node: Node | None) -> str:
        if node is None:
            return ""
        return next(
            (self.text(n) for n in walk(node) if self.class_scope(self.text(n)) is not None), ""
        )

    def _assignments(self) -> None:
        for node in walk(self.context.root):
            left, right = self.syntax.assignment(node)
            if left is not None:
                self._assign(left, right, self.syntax.annotation(node))

    def _assign(self, target: Node, value: Node | None, annotation: Node | None) -> None:
        targets = self.syntax.assignment_targets(target)
        if targets != (target,):
            for child in targets:
                self._assign(child, value, annotation)
            return
        symbol = self._assignment_symbol(target)
        if symbol is not None:
            if target not in symbol.writes:
                symbol.writes.append(target)
            if self.syntax.element_target(target):
                return
            if symbol.kind != "function":
                symbol.value = value
                symbol.annotation = annotation or symbol.annotation
            symbol.type_name = self._declared_type(symbol.annotation) or self._value_type(value)
            symbol.class_scope = self._annotation_scope(symbol.annotation) or self.value_scope(
                value
            )

    def _assignment_symbol(self, target: Node) -> Symbol | None:
        scope = self.locations.get(target.id, 0)
        symbol = self.resolve(target)
        if self.syntax.identifier(target) and self._declares(target, symbol, scope):
            kind: SymbolKind = "field" if self.scopes[scope].owner else "variable"
            return self._bind(target, kind, scope)
        if self.syntax.member_expression(target) and symbol is None:
            return self._new_member(target)
        return symbol

    def _declares(self, target: Node, symbol: Symbol | None, scope: int) -> bool:
        if symbol is None:
            return True
        local = self.scopes[scope].symbols.get(self.text(target))
        if local is not None:
            return local.kind == "import" and local.node != target
        return self.syntax.declares_local(target)

    def _value_type(self, value: Node | None) -> str:
        if value is None:
            return ""
        value = self.syntax.single_value(value)
        node = self._spelled_value_type(value)
        if node is not None:
            return self._declared_type(self.syntax.element_type(node) or node)
        callee = self.syntax.constructor(value)
        if callee is not None:
            return self._declared_type(callee)
        symbol = self.resolve(value)
        return symbol.type_name if symbol is not None else ""

    def _spelled_value_type(self, value: Node) -> Node | None:
        """Accept a spelled value type only where no declared binding stands behind it."""
        node = self.syntax.value_type_node(value)
        if node is None or self._shadowed_call(value) or self._shadowed_name(node):
            return None
        return node

    def _shadowed_name(self, node: Node) -> bool:
        """Report whether a declared non-class binding owns a spelled type name."""
        symbol = self.resolve(node)
        return symbol is not None and symbol.kind != "class"

    def _shadowed_call(self, value: Node) -> bool:
        """Report whether a real call target already owns this value's type."""
        current: Node | None = value
        while current is not None:
            callee = self.syntax.constructor(current) if self.syntax.is_call(current) else None
            if callee is not None:
                return self._declared_call_target(callee)
            current = self.syntax.wrapped_value(current)
        return False

    def _declared_call_target(self, callee: Node) -> bool:
        """Outrank spelling whenever the call target resolves to a declared symbol."""
        return self.resolve(callee) is not None or self._call_scope(callee) is not None

    def _member(self, node: Node) -> Symbol | None:
        receiver, name = self.syntax.member_parts(node)
        if receiver is None or name is None:
            return None
        if self.syntax.base_receiver(receiver):
            return self._base_member(receiver, self.text(name))
        scope = self.value_scope(receiver)
        owner = self.resolve(receiver)
        static = owner is not None and (
            owner.kind == "class" or self.syntax.static_member(owner.node)
        )
        return self.member(scope, self.text(name), static) if scope is not None else None

    def _base_member(self, receiver: Node, name: str) -> Symbol | None:
        callee = self.syntax.constructor(receiver)
        if callee is not None and self.resolve(callee) is not None:
            return None
        current: int | None = self.locations.get(receiver.id, 0)
        static = False
        while current is not None:
            scope = self.scopes[current]
            if self.syntax.function(scope.node):
                static = self.syntax.static_member(scope.node)
            if scope.owner:
                return next(
                    (member for base in scope.bases if (member := self.member(base, name, static))),
                    None,
                )
            current = scope.parent
        return None

    def member(self, scope: Scope, name: str, static: bool = False) -> Symbol | None:
        pending = [scope]
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current.node.id in seen:
                continue
            seen.add(current.node.id)
            symbol = current.static_symbols.get(name) if static else current.symbols.get(name)
            if symbol is not None:
                return symbol
            pending.extend(current.bases)
        return self.member(scope, name) if static else None

    def class_scope(self, name: str) -> Scope | None:
        local = self.classes.get(name)
        return self.scopes[local] if local is not None else self.imported_classes.get(name)

    def value_scope(self, value: Node | None) -> Scope | None:
        if value is None:
            return None
        value = self.syntax.single_value(value)
        node = self._spelled_value_type(value)
        if node is not None:
            return self._annotation_scope(node)
        callee = self.syntax.constructor(value)
        if callee is not None:
            return self._call_scope(callee)
        symbol = self.resolve(value)
        return symbol.class_scope if symbol is not None else None

    def _call_scope(self, callee: Node) -> Scope | None:
        symbol = self.resolve(callee)
        if symbol is not None:
            return symbol.class_scope
        receiver, name = self.syntax.member_parts(callee)
        if (
            receiver is not None
            and name is not None
            and self.syntax.collection_values(self.text(name))
        ):
            return self.value_scope(receiver)
        return None

    def refresh(self) -> None:
        """Resolve references after peer declarations and imported types are connected."""
        self._receivers()
        self._inheritance()
        self._assignments()
        self._iterations()
        self._reads()

    def _inheritance(self) -> None:
        for scope in self.scopes:
            if not scope.owner:
                continue
            scope.bases.clear()
            for bases in self.syntax.inherited_types(scope.node):
                self._bases(scope, bases)

    def _bases(self, scope: Scope, node: Node) -> None:
        scope.abstract = scope.abstract or self.syntax.abstract_base(self.text(node))
        symbol = self.resolve(node)
        if symbol is not None and symbol.library:
            scope.externally_used = True
        parent = self._base_scope(node)
        if parent is None or parent.node.id == scope.node.id:
            return
        if all(base.node.id != parent.node.id for base in scope.bases):
            scope.bases.append(parent)
        scope.externally_used = scope.externally_used or parent.externally_used

    def _base_scope(self, node: Node) -> Scope | None:
        symbol = self.resolve(node)
        return symbol.class_scope if symbol is not None and symbol.kind == "class" else None

    def _new_member(self, node: Node) -> Symbol | None:
        receiver, name = self.syntax.member_parts(node)
        owner = self.resolve(receiver) if receiver is not None else None
        if owner is None or name is None:
            return None
        for scope_id, scope in enumerate(self.scopes):
            if scope is owner.class_scope:
                parameter = scope.parameter_properties.get(self.text(name))
                return parameter or self._bind(name, "field", scope_id)
        return None

    def _iterations(self) -> None:
        for node in walk(self.context.root):
            targets, iterable = self.syntax.iteration(node)
            if iterable is None:
                continue
            owner = self.value_scope(iterable)
            for name in targets:
                symbol = self._assignment_symbol(name)
                if symbol is not None:
                    symbol.class_scope = owner
                    self.declarations.add(name.id)

    def _reads(self) -> None:
        self.unresolved_reads.clear()
        for node in walk(self.context.root):
            if node.id in self.declarations or self.in_annotation(node):
                continue
            if not self.syntax.identifier(node) and not self.syntax.member_expression(node):
                continue
            symbol = self.resolve(node)
            if not self.syntax.read(node):
                continue
            if symbol is not None:
                if node not in symbol.reads:
                    symbol.reads.append(node)
            if self.syntax.member_expression(node):
                self._unresolved_member(node, symbol)

    def _unresolved_member(self, node: Node, symbol: Symbol | None) -> None:
        receiver, name = self.syntax.member_parts(node)
        owner = self.resolve(receiver) if receiver is not None else None
        abstract = (
            owner is not None and owner.class_scope is not None and owner.class_scope.abstract
        )
        if name is not None and (symbol is None or abstract):
            self.unresolved_reads.add(self.text(name))

    def in_annotation(self, node: Node) -> bool:
        return self.syntax.in_annotation(node)
