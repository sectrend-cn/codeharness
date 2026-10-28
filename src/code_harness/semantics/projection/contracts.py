"""Narrow syntax facts retaining the original tree and concrete field associations."""

from dataclasses import dataclass
from typing import Literal, Protocol

from tree_sitter import Node

from code_harness.semantics.index import SemanticIndex


@dataclass(frozen=True)
class FieldKey:
    """A static field name and the language's distinct access operation."""

    name: str
    access: Literal["member", "item"] = "member"

    def __hash__(self) -> int:
        """Hash the same name and access operation used by field equality."""
        return hash((self.name, self.access))


@dataclass(frozen=True)
class Property:
    """A statically named field on an unevaluated receiver expression."""

    receiver: Node
    key: FieldKey


@dataclass(frozen=True)
class Primitive:
    """Keep literal kinds distinct without coercing booleans, numbers or strings."""

    kind: Literal["boolean", "number", "string", "absent", "null"]
    value: str


@dataclass(frozen=True)
class Guard:
    """Describe the branch that establishes presence or a literal equality."""

    source: Property
    when: bool
    literal: Primitive
    description: str


@dataclass(frozen=True)
class Branches:
    """Retain a predicate and its two possible actions."""

    condition: Node
    consequence: Node
    alternative: Node | None


@dataclass(frozen=True)
class Write:
    """One named destination field and its original value expression."""

    receiver: Node | None
    key: FieldKey
    value: Node


class ProjectionSyntax(Protocol):
    """Language-owned interpretation consumed by shared matching and grouping."""

    def region(self, node: Node) -> bool: ...
    def construction(self, node: Node) -> bool: ...
    def ignored(self, node: Node) -> bool: ...
    def unwrap(self, node: Node) -> Node: ...
    def branches(self, node: Node) -> Branches | None: ...
    def guard(self, node: Node, index: SemanticIndex) -> Guard | None: ...
    def empty(self, node: Node | None) -> bool: ...
    def write(self, node: Node, construction: bool, index: SemanticIndex) -> Write | None: ...
    def property(self, node: Node, index: SemanticIndex) -> Property | None: ...
    def primitive(self, node: Node, index: SemanticIndex) -> Primitive | None: ...
    def immutable_alias(self, node: Node) -> bool: ...
    def destination(self, node: Node, index: SemanticIndex) -> str: ...
