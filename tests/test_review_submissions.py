"""Incremental finding acceptance, retry identity, and terminal review semantics."""

from pathlib import Path

import pytest

from code_harness.diagnostics import AnalysisError
from code_harness.review.mcp_server import ReviewSubmissionServer
from code_harness.review.submission_models import (
    FindingSubmission,
    ReviewCompletion,
    ReviewScope,
)
from code_harness.review.submissions import SubmissionStore


@pytest.fixture
def store(tmp_path: Path) -> SubmissionStore:
    return SubmissionStore.create(
        tmp_path, ReviewScope(path="app.py", rule_id="review.state", line_bytes=(20, 10))
    )


def test_each_acknowledged_finding_is_persisted_before_completion(
    store: SubmissionStore, tmp_path: Path
) -> None:
    receipt = store.submit(
        FindingSubmission(submission_id="one", line=1, column=1, message="Evidence")
    )
    assert receipt.accepted_count == 1
    assert (tmp_path / "events.jsonl").read_text().count("\n") == 1
    loaded = SubmissionStore(tmp_path)
    receipt = loaded.submit(
        FindingSubmission(submission_id="one", line=1, column=1, message="Evidence")
    )
    assert receipt.duplicate
    with pytest.raises(AnalysisError, match="finish_review"):
        loaded.result()
    loaded.finish(ReviewCompletion(status="complete", summary="Done", expected_findings=1))
    result = SubmissionStore(tmp_path).result()
    assert result.findings[0].path == "app.py"
    assert result.findings[0].rule == "review.state"


def test_retry_cannot_change_evidence(store: SubmissionStore) -> None:
    store.submit(FindingSubmission(submission_id="one", line=1, column=1, message="Evidence"))
    with pytest.raises(AnalysisError, match="different evidence"):
        store.submit(FindingSubmission(submission_id="one", line=1, column=1, message="Other"))


def test_completion_checks_count_and_is_idempotent(store: SubmissionStore) -> None:
    with pytest.raises(AnalysisError, match="count"):
        store.finish(ReviewCompletion(status="complete", summary="Done", expected_findings=1))
    completion = ReviewCompletion(status="complete", summary="Clean review", expected_findings=0)
    assert not store.finish(completion).duplicate
    assert store.finish(completion).duplicate
    with pytest.raises(AnalysisError, match="different completion"):
        store.finish(
            ReviewCompletion(status="incomplete", summary="Missing context", expected_findings=0)
        )
    with pytest.raises(AnalysisError, match="already finished"):
        store.submit(FindingSubmission(submission_id="late", line=1, column=1, message="Late"))


@pytest.mark.parametrize(
    ("line", "column", "message"), [(3, 1, "Evidence"), (1, 22, "Evidence"), (1, 1, " ")]
)
def test_submission_validates_snapshot_locations(
    store: SubmissionStore, line: int, column: int, message: str
) -> None:
    with pytest.raises(AnalysisError):
        store.submit(
            FindingSubmission(submission_id="bad", line=line, column=column, message=message)
        )


@pytest.mark.usefixtures("store")
def test_tool_methods_return_only_small_receipts(tmp_path: Path) -> None:
    server = ReviewSubmissionServer(tmp_path)
    receipt = server.submit_finding("one", 1, 1, "Evidence" * 1000)
    assert receipt.accepted_count == 1
    assert len(receipt.model_dump_json()) < 100
    assert server.finish_review("complete", "Done", 1).accepted_count == 1


def test_incomplete_tool_completion_preserves_findings(store: SubmissionStore) -> None:
    store.submit(FindingSubmission(submission_id="one", line=1, column=1, message="Evidence"))
    store.finish(ReviewCompletion(status="incomplete", summary="Need caller", expected_findings=1))
    assert store.result().status == "incomplete"
    assert len(store.result().findings) == 1


def test_empty_completion_summary_is_rejected(store: SubmissionStore) -> None:
    with pytest.raises(AnalysisError, match="meaningful summary"):
        store.finish(ReviewCompletion(status="complete", summary=" ", expected_findings=0))


@pytest.mark.usefixtures("store")
def test_tool_bounds_message_size(tmp_path: Path) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReviewSubmissionServer(tmp_path).submit_finding("large", 1, 1, "x" * 8193)
