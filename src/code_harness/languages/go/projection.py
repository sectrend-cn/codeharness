"""Go nil/literal guarded selector assignments."""

from tree_sitter import Node

from code_harness.languages.projection_syntax import GrammarProjection
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.projection.contracts import Primitive


class GoProjection(GrammarProjection):
    """Limit projection to field selectors; map indexes and initializer guards are excluded."""

    blocks = frozenset({"block", "statement_list"})
    members = frozenset({"selector_expression"})
    regions = frozenset({"statement_list"})
    assignments = frozenset({"assignment_statement"})
    nulls = frozenset[str]()
    absent = frozenset({"nil"})
    numbers = frozenset({"int_literal", "float_literal"})
    strings = frozenset({"interpreted_string_literal", "raw_string_literal"})

    def primitive(self, node: Node, index: SemanticIndex) -> Primitive | None:
        node = self.unwrap(node)
        if node.type in self.booleans:
            if index.lookup(index.text(node), index.locations.get(node.id, 0)) is not None:
                return None
        return super().primitive(node, index)
