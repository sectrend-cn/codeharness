"""Review guidelines, evidence validation, and rule registration behavior."""

from dataclasses import dataclass

import pytest

from code_harness.diagnostics import AnalysisError, Finding
from code_harness.plugins.builtins import builtin_analyzers
from code_harness.policy.models import Policy
from code_harness.review.contracts import (
    AgentReviewRule,
    ReviewGuideline,
    ReviewRequest,
    ReviewResult,
)
from code_harness.review.prompt import ReviewPrompt
from code_harness.review.rules import PromptReviewRule
from code_harness.source import Language, Source

_GUIDELINE = ReviewGuideline(
    "review.ownership",
    "Review mutable state ownership",
    ("Find state with multiple mutation owners.", "Cite the specific declaration."),
)
_SOURCE = Source("app.py", b"state: list[int] = []\n", Language.PYTHON)


@dataclass
class FixtureReviewer:
    """Retain exact concrete requests to verify guideline and snapshot ownership."""

    result: ReviewResult
    request: ReviewRequest | None = None

    def review(self, request: ReviewRequest) -> ReviewResult:
        self.request = request
        return self.result


def _rule(reviewer: FixtureReviewer) -> AgentReviewRule:
    return PromptReviewRule("test.review", _GUIDELINE, reviewer)


def test_agent_rule_registers_and_retains_snapshot_and_guidelines() -> None:
    reviewer = FixtureReviewer(
        ReviewResult(status="complete", summary="No violations", findings=())
    )
    analyzer = builtin_analyzers()[0]
    analyzer.bundles.register(_rule(reviewer))
    assert analyzer.analyze(_SOURCE, Policy()) == ()
    assert reviewer.request == ReviewRequest(_SOURCE, _GUIDELINE)


@pytest.mark.parametrize(
    "result",
    [
        ReviewResult(status="incomplete", summary="Need caller evidence", findings=()),
        ReviewResult(status="complete", summary=" ", findings=()),
    ],
)
def test_unresolved_review_cannot_pass(result: ReviewResult) -> None:
    analyzer = builtin_analyzers()[0]
    analyzer.bundles.register(_rule(FixtureReviewer(result)))
    with pytest.raises(AnalysisError, match="did not complete"):
        analyzer.analyze(_SOURCE, Policy())


@pytest.mark.parametrize(
    ("path", "rule", "line", "column", "message"),
    [
        ("different.py", "review.ownership", 1, 1, "evidence"),
        ("app.py", "unregistered", 1, 1, "evidence"),
        ("app.py", "review.ownership", 0, 1, "evidence"),
        ("app.py", "review.ownership", 2, 1, "evidence"),
        ("app.py", "review.ownership", 1, 0, "evidence"),
        ("app.py", "review.ownership", 1, 99, "evidence"),
        ("app.py", "review.ownership", 1, 1, " "),
    ],
)
def test_invalid_agent_evidence_is_rejected(
    path: str, rule: str, line: int, column: int, message: str
) -> None:
    finding = Finding(path=path, line=line, column=column, rule=rule, message=message)
    result = ReviewResult(status="complete", summary="Reviewed", findings=(finding,))
    analyzer = builtin_analyzers()[0]
    analyzer.bundles.register(_rule(FixtureReviewer(result)))
    with pytest.raises(AnalysisError):
        analyzer.analyze(_SOURCE, Policy())


def test_prompt_contains_guidelines_source_and_explicit_result_contract() -> None:
    prompt = ReviewPrompt().render(ReviewRequest(_SOURCE, _GUIDELINE))
    assert _GUIDELINE.objective in prompt
    assert all(instruction in prompt for instruction in _GUIDELINE.instructions)
    assert _SOURCE.content.decode() in prompt
    assert "untrusted evidence" in prompt
    assert "submit_finding" in prompt
    assert "finish_review" in prompt
    assert "do not" in prompt.lower()
    assert "final findings array" in prompt
    assert "one-based lines and UTF-8 byte columns" in prompt


@pytest.mark.parametrize(
    ("identity", "objective", "instructions"),
    [
        ("", "objective", ("review",)),
        ("rule", "", ("review",)),
        ("rule", "objective", ()),
        ("rule", "objective", (" ",)),
    ],
)
def test_review_guidelines_require_meaningful_instructions(
    identity: str, objective: str, instructions: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError):
        ReviewGuideline(identity, objective, instructions)
