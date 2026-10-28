"""Match explicit instance outputs against grammar-proven lexical owners."""

from dataclasses import dataclass

from tree_sitter import Node

from code_harness.semantics.encoding_options import InstanceOutput
from code_harness.semantics.index import SemanticIndex


@dataclass(frozen=True)
class InstanceOutputs:
    """Require exact snapshot identity and a unique class before permitting a slot."""

    index: SemanticIndex
    declarations: tuple[InstanceOutput, ...]

    def permits(self, owner: Node | None, member: Node | None, position: int) -> bool:
        class_name = self._class_name(owner)
        if class_name is None or member is None:
            return False
        return any(
            output.path == self.index.context.source.path
            and output.class_name == class_name
            and output.member == self.index.text(member)
            and position in output.arguments
            for output in self.declarations
        )

    def _class_name(self, owner: Node | None) -> str | None:
        if owner is None:
            return None
        name = self.index.syntax.class_name(owner)
        if name is None:
            return None
        class_name = self.index.text(name)
        owners = [scope.node for scope in self.index.scopes if scope.owner == class_name]
        return class_name if owners == [owner] else None
