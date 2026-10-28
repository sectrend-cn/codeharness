"""Language-independent serialization checks using aliases and output-flow evidence."""

from dataclasses import dataclass
from typing import Protocol

from tree_sitter import Node

from code_harness.analysis.context import TreeContext
from code_harness.analysis.requirements import RuleRequirements
from code_harness.diagnostics import Finding
from code_harness.parsing.treesitter import walk
from code_harness.semantics.aliases import NameSyntax, QualifiedNames
from code_harness.semantics.boundaries import BoundaryEvidence
from code_harness.semantics.encoding_members import InstanceOutputs
from code_harness.semantics.encoding_options import BROAD_TYPE, EncodingOptions
from code_harness.semantics.flow import Destination, ValueFlow
from code_harness.semantics.index import SemanticIndex
from code_harness.semantics.model import ParameterSlot


class EncodingSyntax(Protocol):
    """Keep serializer identities, call syntax and terminal APIs with their grammar."""

    @property
    def names(self) -> NameSyntax: ...
    def instance_owner(self, callee: Node, index: SemanticIndex) -> Node | None: ...
    def instance_member(self, callee: Node, index: SemanticIndex) -> Node | None: ...
    def qualified(self, callee: Node, names: QualifiedNames) -> str: ...
    def result_binding(self, node: Node, names: QualifiedNames) -> Node | None: ...
    def single_result(self, name: str) -> bool: ...
    def encoder(self, name: str, callee: Node) -> bool: ...
    def decoder(self, name: str) -> bool: ...
    def consumer(self, node: Node, index: SemanticIndex) -> Node | None: ...
    def terminal(self, callee: Node, value: Node, names: QualifiedNames) -> bool: ...
    def argument(self, callee: Node, value: Node) -> ParameterSlot | None: ...


@dataclass(frozen=True)
class EncodingDestinations:
    """Reject reconstruction before considering external or terminal output evidence."""

    names: QualifiedNames
    boundary: BoundaryEvidence
    syntax: EncodingSyntax
    options: EncodingOptions

    def classify(self, node: Node) -> Destination:
        callee = self.syntax.consumer(node, self.names.index)
        if callee is not None:
            name = self.syntax.qualified(callee, self.names)
            if self.syntax.decoder(name) or name in self.options.decoders:
                return "reject"
            if self.syntax.terminal(callee, node, self.names) or self._configured(callee, node):
                return "permit"
        return self.boundary.classify(node)

    def _configured(self, callee: Node, value: Node) -> bool:
        name = self.syntax.qualified(callee, self.names)
        slot = self.syntax.argument(callee, value)
        if slot is None:
            return False
        if slot.kind == "positional" and self.options.instance_outputs:
            owner = self.syntax.instance_owner(callee, self.names.index)
            if InstanceOutputs(self.names.index, self.options.instance_outputs).permits(
                owner, self.syntax.instance_member(callee, self.names.index), slot.position
            ):
                return True
        return any(
            output.call == name
            and (
                slot.kind == "positional"
                and slot.position in output.arguments
                or slot.kind == "keyword"
                and slot.name in output.keywords
            )
            for output in self.options.outputs
        )


@dataclass(frozen=True)
class EncodingRule:
    """Own serialization erasure policy for any supplied grammar capability."""

    syntax: EncodingSyntax
    name: str = "builtin.encoding"
    api_version: int = 2
    requirements: RuleRequirements = RuleRequirements(semantic_evidence=True)
    rule_ids: tuple[str, ...] = BROAD_TYPE.rule_ids

    def check(self, context: TreeContext) -> tuple[Finding, ...]:
        boundary = context.require_boundary()
        index = boundary.index
        names = QualifiedNames(index, self.syntax.names)
        options = context.policy.checkers.type_broad.encoding
        outputs = ValueFlow(index, EncodingDestinations(names, boundary, self.syntax, options))
        findings: list[Finding] = []
        for node in walk(context.root):
            callee = index.syntax.call(node)
            if callee is None:
                continue
            name = self.syntax.qualified(callee, names)
            if not (self.syntax.encoder(name, callee) or name in options.encoders):
                continue
            if self._permitted(node, name, names, outputs):
                continue
            findings.append(
                Finding(
                    path=context.source.path,
                    line=node.start_point.row + 1,
                    column=node.start_point.column + 1,
                    rule=BROAD_TYPE.name,
                    message=f"Preserve concrete values internally; {name} erases their contract",
                )
            )
        return tuple(findings)

    def _permitted(self, node: Node, name: str, names: QualifiedNames, outputs: ValueFlow) -> bool:
        target = self.syntax.result_binding(node, names)
        if target is not None:
            return outputs.binding_permitted(target, node)
        return self.syntax.single_result(name) and outputs.permitted(node)
