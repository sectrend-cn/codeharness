"""Java concrete-type and suppression policy."""

import re
from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.languages.comments import GrammarComments
from code_harness.languages.java.type_syntax import JavaTypeChecks
from code_harness.languages.type_checks import TypeMarkers
from code_harness.parsing.treesitter import field, spelling, walk
from code_harness.policy.type_options import ASSERTION
from code_harness.semantics.encoding import EncodingRule
from code_harness.semantics.encoding_options import BROAD_TYPE
from code_harness.source import Source


@dataclass(frozen=True)
class JavaTypeRule:
    """Reject root-object erasure, unbounded wildcards and reference assertions."""

    encoding: EncodingRule
    name: str = "builtin.types.java"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements(semantic_evidence=True)
    rule_ids: tuple[str, ...] = (BROAD_TYPE.name, ASSERTION.name)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        return (*TypeMarkers(context).check(JavaTypeChecks(context)), *self.encoding.check(context))


class JavaSuppressions(GrammarComments):
    """Recognize Java checker annotations and comment directives."""

    def comments(self, root: Node) -> tuple[Node, ...]:
        return tuple(node for node in walk(root) if node.type in {"line_comment", "block_comment"})

    def disabled_types(self, context: TreeContext) -> tuple[Node, ...]:
        return tuple(node for node in walk(context.root) if self._suppression(node, context.source))

    def _suppression(self, node: Node, source: Source) -> bool:
        if node.type in {"annotation", "marker_annotation"}:
            name = field(node, "name")
            return name is not None and spelling(name, source).rsplit(".", 1)[-1] in {
                "SuppressWarnings",
                "SuppressFBWarnings",
            }
        return (
            node.type in {"line_comment", "block_comment"}
            and re.search(
                r"(?<!\w)(?:NOSONAR|CHECKSTYLE\s*:\s*OFF|noinspection)\b",
                spelling(node, source),
                re.IGNORECASE,
            )
            is not None
        )
