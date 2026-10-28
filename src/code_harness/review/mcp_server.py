"""Private stdio MCP tools advertised to the ACP reviewer for incremental submission."""

import fcntl
import sys
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from code_harness.review.submission_models import (
    FindingSubmission,
    ReviewCompletion,
    SubmissionReceipt,
)
from code_harness.review.submissions import SubmissionStore


class ReviewSubmissionServer:
    """Expose only bounded submission and completion tools, with one journal writer."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._store = SubmissionStore(directory)
        self._server = FastMCP[None]("code-harness-review")
        annotations = ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
        )
        self._server.add_tool(self.submit_finding, annotations=annotations)
        self._server.add_tool(self.finish_review, annotations=annotations)

    def submit_finding(
        self, submission_id: str, line: int, column: int, message: str
    ) -> SubmissionReceipt:
        """Submit one finding now; reuse its ID for retries without resending earlier findings."""
        submission = FindingSubmission(
            submission_id=submission_id, line=line, column=column, message=message
        )
        return self._store.submit(submission)

    def finish_review(
        self, status: Literal["complete", "incomplete"], summary: str, expected_findings: int
    ) -> SubmissionReceipt:
        """Finish once all submissions are acknowledged, including zero for a clean review."""
        completion = ReviewCompletion(
            status=status, summary=summary, expected_findings=expected_findings
        )
        return self._store.finish(completion)

    def run(self) -> None:
        with (self._directory / "writer.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._store = SubmissionStore(self._directory)
            self._server.run(transport="stdio")


if __name__ == "__main__":
    ReviewSubmissionServer(Path(sys.argv[1])).run()
