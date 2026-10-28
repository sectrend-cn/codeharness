"""Concrete capability requirements owned by rule execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleRequirements:
    """Declare whether a rule consumes resolved semantic and boundary evidence."""

    semantic_evidence: bool = False
