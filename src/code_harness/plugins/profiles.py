"""Application-owned required coverage and explicit unavailable analyses."""

from dataclasses import dataclass

from code_harness.diagnostics import AnalysisError


@dataclass(frozen=True)
class AnalysisProfile:
    """Separate execution requirements from grammar identity and discovery."""

    required_rules: tuple[str, ...]
    optional_unavailable: tuple[str, ...] = ()

    def validate(self, rules: tuple[str, ...]) -> None:
        """Validate required coverage independently of policy enable flags."""
        required = self.required_rules
        if not required or len(set(required)) != len(required) or any(not r for r in required):
            raise AnalysisError("Invalid required rules for analysis profile")
        missing = set(required).difference(rules)
        if missing:
            raise AnalysisError(f"Analyzer is missing rules: {', '.join(sorted(missing))}")
        if set(self.optional_unavailable).intersection(rules):
            raise AnalysisError("Available rules cannot be declared unavailable")
