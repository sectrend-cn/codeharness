"""Interpret Java type erasure with explicit standard-library name evidence."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.languages.java.semantic_syntax import JavaSemanticSyntax
from code_harness.parsing.treesitter import field, spelling
from code_harness.policy.type_options import ASSERTION
from code_harness.semantics.encoding_options import BROAD_TYPE
from code_harness.source import Source

_RAW_COLLECTIONS = frozenset(
    {
        "Iterable",
        "Collection",
        "List",
        "Set",
        "Map",
        "Iterator",
        "ListIterator",
        "ArrayList",
        "LinkedList",
        "HashSet",
        "TreeSet",
        "HashMap",
        "TreeMap",
        "Queue",
        "Deque",
        "Optional",
        "Comparator",
        "Comparable",
    }
)


@dataclass(frozen=True)
class JavaTypeChecks:
    """Keep type-name resolution at the Java grammar boundary."""

    context: TreeContext

    def issue(self, node: Node, source: Source) -> tuple[str, str] | None:
        if node.type in {"type_identifier", "scoped_type_identifier"}:
            return self._type(node, source)
        if node.type == "wildcard" and not any(
            child.type in {"extends", "super"} for child in node.children
        ):
            return BROAD_TYPE.name, "An unbounded wildcard erases the element contract"
        if node.type == "cast_expression":
            target = field(node, "type")
            if target is not None and target.type not in {
                "integral_type",
                "floating_point_type",
                "boolean_type",
            }:
                return ASSERTION.name, "Preserve or validate the contract instead of casting it"
        return None

    def _type(self, node: Node, source: Source) -> tuple[str, str] | None:
        parent = node.parent
        if parent is not None and parent.type in {"scoped_type_identifier", "type_parameter"}:
            return None
        name = self._standard_name(node, source)
        if name == "java.lang.Object":
            return BROAD_TYPE.name, "Use a concrete contract instead of Object"
        if parent is not None and parent.type == "generic_type":
            return None
        package, _, simple = name.rpartition(".")
        if package in {"java.lang", "java.util"} and simple in _RAW_COLLECTIONS:
            return BROAD_TYPE.name, f"Declare concrete type arguments for {simple}"
        return None

    def _standard_name(self, node: Node, source: Source) -> str:
        name = spelling(node, source)
        if "." in name:
            return name
        symbol = self.context.require_index().resolve(node)
        if symbol is not None and symbol.kind != "import":
            return ""
        if self._type_parameter(node, name, source):
            return ""
        for entry in JavaSemanticSyntax().imports(self.context):
            if entry.name == name:
                return entry.module
        if name in {"Object", "Iterable", "Comparable"}:
            return f"java.lang.{name}"
        return ""

    def _type_parameter(self, node: Node, name: str, source: Source) -> bool:
        current = node.parent
        while current is not None:
            parameters = field(current, "type_parameters")
            declarations = parameters.named_children if parameters is not None else ()
            for parameter in declarations:
                declared = next(
                    (n for n in parameter.named_children if n.type == "type_identifier"), None
                )
                if declared is not None and spelling(declared, source) == name:
                    return True
            current = current.parent
        return False
