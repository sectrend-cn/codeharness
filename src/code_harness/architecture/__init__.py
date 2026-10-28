"""Architecture contracts and dependency checks."""

from typing import TYPE_CHECKING

__all__ = ["ArchitectureRule"]

if TYPE_CHECKING:
    from code_harness.architecture.rules import ArchitectureRule


def __getattr__(name: str) -> type["ArchitectureRule"]:
    """Load the public rule class without coupling option imports to execution."""
    if name != "ArchitectureRule":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from code_harness.architecture.rules import ArchitectureRule

    return ArchitectureRule
