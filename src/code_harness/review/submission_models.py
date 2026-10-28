"""Typed tool inputs, acknowledgements, and persisted review events."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from code_harness.diagnostics import AnalysisError, Finding
from code_harness.review.contracts import ReviewRequest


class SubmissionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ReviewScope(SubmissionModel):
    """Bind submission evidence to the exact rule and source location bounds."""

    path: str
    rule_id: str
    line_bytes: tuple[int, ...]

    @classmethod
    def from_request(cls, request: ReviewRequest) -> "ReviewScope":
        return cls(
            path=request.source.path,
            rule_id=request.guideline.rule_id,
            line_bytes=tuple(len(line) for line in request.source.content.splitlines()) or (0,),
        )

    def validate_finding(self, finding: Finding) -> None:
        if finding.path != self.path or finding.rule != self.rule_id:
            raise AnalysisError("Agent finding does not belong to the requested source and rule")
        if not 1 <= finding.line <= len(self.line_bytes):
            raise AnalysisError("Agent finding line is outside the source snapshot")
        if not 1 <= finding.column <= self.line_bytes[finding.line - 1] + 1:
            raise AnalysisError("Agent finding column is outside the source snapshot")
        if not finding.message.strip():
            raise AnalysisError("Agent finding requires an evidence-bearing message")


class FindingSubmission(SubmissionModel):
    """One bounded submission with a stable retry identity."""

    submission_id: str = Field(min_length=1, max_length=128)
    line: int = Field(ge=1)
    column: int = Field(ge=1)
    message: str = Field(min_length=1, max_length=8192)


class ReviewCompletion(SubmissionModel):
    status: Literal["complete", "incomplete"]
    summary: str = Field(min_length=1, max_length=2048)
    expected_findings: int = Field(ge=0)


class SubmissionReceipt(SubmissionModel):
    accepted_count: int
    duplicate: bool


class FindingEvent(SubmissionModel):
    kind: Literal["finding"] = "finding"
    submission_id: str
    finding: Finding


class CompletionEvent(SubmissionModel):
    kind: Literal["completion"] = "completion"
    completion: ReviewCompletion


type ReviewEvent = Annotated[FindingEvent | CompletionEvent, Field(discriminator="kind")]
