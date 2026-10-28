"""Run registered language analyzers over immutable source snapshots."""

from functools import lru_cache

from code_harness.diagnostics import Finding
from code_harness.models import Policy, Source
from code_harness.plugins.builtins import builtin_registry
from code_harness.plugins.registry import AnalyzerRegistry


@lru_cache(maxsize=1)
def registry() -> AnalyzerRegistry:
    """Compose the required built-in analyzers once at the application boundary."""
    return builtin_registry()


def check(
    source: Source, policy: Policy, analyzers: AnalyzerRegistry | None = None
) -> tuple[Finding, ...]:
    """Execute the registered analyzer; missing or failed analyzers are errors."""
    return (analyzers if analyzers is not None else registry()).analyze(source, policy)
