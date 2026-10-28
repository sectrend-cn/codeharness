"""Incremental review journal with idempotent submissions and explicit completion."""

import os
from pathlib import Path

from pydantic import TypeAdapter

from code_harness.diagnostics import AnalysisError, Finding
from code_harness.review.contracts import ReviewResult
from code_harness.review.submission_models import (
    CompletionEvent,
    FindingEvent,
    FindingSubmission,
    ReviewCompletion,
    ReviewEvent,
    ReviewScope,
    SubmissionReceipt,
)


class SubmissionStore:
    """Own one review's append-only evidence and terminal completion state."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._scope = ReviewScope.model_validate_json((directory / "scope.json").read_bytes())
        self._findings: dict[str, Finding] = {}
        self._completion: ReviewCompletion | None = None
        self._load()

    @classmethod
    def create(cls, directory: Path, scope: ReviewScope) -> "SubmissionStore":
        with (directory / "scope.json").open("x", encoding="utf-8") as output:
            output.write(scope.model_dump_json())
        return cls(directory)

    def submit(self, submission: FindingSubmission) -> SubmissionReceipt:
        finding = Finding(
            path=self._scope.path,
            rule=self._scope.rule_id,
            line=submission.line,
            column=submission.column,
            message=submission.message,
        )
        self._scope.validate_finding(finding)
        previous = self._findings.get(submission.submission_id)
        if previous is not None:
            if previous != finding:
                raise AnalysisError("Submission ID already belongs to different evidence")
            return SubmissionReceipt(accepted_count=len(self._findings), duplicate=True)
        if self._completion is not None:
            raise AnalysisError("Review is already finished")
        event = FindingEvent(submission_id=submission.submission_id, finding=finding)
        self._append(event)
        self._findings[submission.submission_id] = finding
        return SubmissionReceipt(accepted_count=len(self._findings), duplicate=False)

    def finish(self, completion: ReviewCompletion) -> SubmissionReceipt:
        if completion.expected_findings != len(self._findings):
            raise AnalysisError("Completion count does not match accepted findings")
        if not completion.summary.strip():
            raise AnalysisError("Completion requires a meaningful summary")
        if self._completion is not None:
            if self._completion != completion:
                raise AnalysisError("Review already has a different completion")
            return SubmissionReceipt(accepted_count=len(self._findings), duplicate=True)
        self._append(CompletionEvent(completion=completion))
        self._completion = completion
        return SubmissionReceipt(accepted_count=len(self._findings), duplicate=False)

    def result(self) -> ReviewResult:
        if self._completion is None:
            raise AnalysisError("Agent did not call finish_review; review is incomplete")
        return ReviewResult(
            status=self._completion.status,
            summary=self._completion.summary,
            findings=tuple(self._findings.values()),
        )

    def _append(self, event: ReviewEvent) -> None:
        with (self._directory / "events.jsonl").open("a", encoding="utf-8") as output:
            output.write(event.model_dump_json() + "\n")
            output.flush()
            os.fsync(output.fileno())

    def _load(self) -> None:
        path = self._directory / "events.jsonl"
        if not path.exists():
            return
        adapter = TypeAdapter[ReviewEvent](ReviewEvent)
        with path.open("rb") as source:
            for raw in source:
                self._replay(adapter.validate_json(raw))

    def _replay(self, event: ReviewEvent) -> None:
        if self._completion is not None:
            raise AnalysisError("Submission journal has entries after completion")
        if isinstance(event, FindingEvent):
            self._scope.validate_finding(event.finding)
            if event.submission_id in self._findings:
                raise AnalysisError("Submission journal contains a duplicate identity")
            self._findings[event.submission_id] = event.finding
        else:
            if event.completion.expected_findings != len(self._findings):
                raise AnalysisError("Submission journal completion count is invalid")
            self._completion = event.completion
