"""Canonical agent-review guidelines, requests, and completed review contracts."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from code_harness.analysis.contracts import RuleBundle
from code_harness.diagnostics import Finding
from code_harness.source import Source


@dataclass(frozen=True)
class ReviewGuideline:
    """A rule owns the exact review objective and evidence requirements."""

    rule_id: str
    objective: str
    instructions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.objective.strip():
            raise ValueError("Review rule identity and objective must be nonempty")
        if not self.instructions or any(not item.strip() for item in self.instructions):
            raise ValueError("Review guidelines require nonempty instructions")


@dataclass(frozen=True)
class ReviewRequest:
    """Keep source bytes concrete until encoding the outbound agent prompt."""

    source: Source
    guideline: ReviewGuideline


class ReviewResult(BaseModel):
    """An explicit completion verdict; an absent or incomplete review cannot pass."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    status: Literal["complete", "incomplete"]
    summary: str = Field(min_length=1)
    findings: tuple[Finding, ...]


class ReviewAgent(Protocol):
    """Invoke a reviewer without exposing transport details to rule behavior."""

    def review(self, request: ReviewRequest) -> ReviewResult: ...


class AgentReviewRule(RuleBundle, Protocol):
    """A registered review rule must expose its owned prompt guidelines."""

    @property
    def guideline(self) -> ReviewGuideline: ...
