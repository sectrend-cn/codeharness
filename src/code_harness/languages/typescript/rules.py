"""Grammar-specific concrete-type policy."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.languages.type_checks import TypeMarkers
from code_harness.parsing.treesitter import spelling
from code_harness.policy.type_options import ASSERTION
from code_harness.semantics.encoding import EncodingRule
from code_harness.semantics.encoding_options import BROAD_TYPE
from code_harness.source import Source


@dataclass(frozen=True)
class TypeScriptTypeRule:
    """Reject unchecked assertions and broad TypeScript contracts."""

    encoding: EncodingRule
    name: str = "builtin.types.typescript"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements(semantic_evidence=True)
    rule_ids: tuple[str, ...] = (ASSERTION.name, BROAD_TYPE.name)

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        return (*TypeMarkers(context).check(self), *self.encoding.check(context))

    def issue(self, node: Node, source: Source) -> tuple[str, str] | None:
        text = spelling(node, source)
        if node.type == "predefined_type" and text in {"any", "unknown", "object"}:
            return BROAD_TYPE.name, f"Use a concrete contract instead of {text}"
        if node.type == "object_type" and all(
            child.type == "comment" for child in node.named_children
        ):
            return BROAD_TYPE.name, "Empty object types do not declare a domain contract"
        if node.type in {"as_expression", "type_assertion"}:
            if node.type == "as_expression" and node.children[-1].type == "const":
                return None
            return ASSERTION.name, "Preserve or validate the contract instead of asserting it"
        if node.type == "non_null_expression":
            return ASSERTION.name, "Represent or handle the missing-value outcome"
        return None
