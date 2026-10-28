"""Consumer-owned syntax evidence for architectural object-design checks."""

from typing import Protocol

from tree_sitter import Node

from code_harness.source import Source


class DesignSyntax(Protocol):
    """Interpret selectors and public module functions without evaluating policy."""

    def dispatch(self, node: Node, source: Source) -> bool: ...
    def module_functions(self, root: Node) -> tuple[Node, ...]: ...
    def function_name(self, node: Node) -> Node | None: ...
