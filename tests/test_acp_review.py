"""Exercise the ACP review lifecycle against a real local stdio subprocess."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from code_harness.cli import main
from code_harness.diagnostics import AnalysisError
from code_harness.plugins.builtins import builtin_analyzers
from code_harness.plugins.registry import AnalyzerRegistry
from code_harness.review.acp import AcpCommand, AcpReviewAgent
from code_harness.review.contracts import ReviewGuideline, ReviewRequest
from code_harness.review.rules import PromptReviewRule
from code_harness.review.wire import InitializeCall
from code_harness.source import Language, Source

_FIXTURE = Path(__file__).parent / "fixtures" / "acp_review_agent.py"
_GUIDELINE = ReviewGuideline(
    "review.ownership", "Review state ownership", ("Cite concrete evidence.",)
)
_REQUEST = ReviewRequest(Source("app.py", b"state: list[int] = []\n", Language.PYTHON), _GUIDELINE)


def _agent(tmp_path: Path, mode: str, timeout: float = 10.0, limit: int = 100000) -> AcpReviewAgent:
    return AcpReviewAgent(
        AcpCommand(
            sys.executable,
            (str(_FIXTURE), mode, str(tmp_path / "record")),
            timeout_seconds=timeout,
            output_limit=limit,
        )
    )


def test_acp_review_negotiates_streams_and_cleans_up(tmp_path: Path) -> None:
    result = _agent(tmp_path, "finding").review(_REQUEST)
    assert result.status == "complete"
    assert result.findings[0].message == "Shared mutable state"
    assert result.findings[0].rule == _GUIDELINE.rule_id
    request = InitializeCall.model_validate_json((tmp_path / "record").read_bytes())
    assert request.params.protocol_version == 1
    capabilities = request.params.client_capabilities
    assert capabilities is not None and not capabilities.terminal
    assert _GUIDELINE.instructions[0] in (tmp_path / "record.prompt").read_text()
    assert not Path((tmp_path / "record.cwd").read_text()).exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int((tmp_path / "record.pid").read_text()), 0)


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("version", "unsupported protocol"),
        ("empty-session", "empty session"),
        ("exit", "closed the stream"),
        ("malformed", "review failed"),
        ("rpc-error", "fixture failure"),
        ("wrong-id", "response ID"),
        ("wrong-session", "unexpected session"),
        ("empty", "did not call finish_review"),
        ("no-finish", "did not call finish_review"),
        ("cancelled", "did not finish"),
        ("permission", "unavailable permissions"),
    ],
)
def test_acp_failures_are_not_clean_reviews(tmp_path: Path, mode: str, message: str) -> None:
    with pytest.raises(AnalysisError, match=message):
        _agent(tmp_path, mode).review(_REQUEST)
    if mode == "permission":
        assert (tmp_path / "record.permission").read_text() == "cancelled"


def test_acp_timeout_reaps_the_agent(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="timed out"):
        _agent(tmp_path, "hang", timeout=2.0).review(_REQUEST)
    with pytest.raises(ProcessLookupError):
        os.kill(int((tmp_path / "record.pid").read_text()), 0)


def test_acp_output_limit_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="limit|review failed"):
        _agent(tmp_path, "oversized", limit=3000).review(_REQUEST)


def test_prompt_limit_fails_before_spawning() -> None:
    agent = AcpReviewAgent(AcpCommand("unused-command", prompt_limit=1))
    with pytest.raises(AnalysisError, match="prompt exceeds"):
        agent.review(_REQUEST)


def test_missing_acp_executable_is_an_error() -> None:
    with pytest.raises(AnalysisError, match="review failed"):
        AcpReviewAgent(AcpCommand("/does-not-exist/acp-agent")).review(_REQUEST)


def test_sync_review_rejects_running_event_loop(tmp_path: Path) -> None:
    async def run() -> None:
        with pytest.raises(AnalysisError, match="event loop"):
            _agent(tmp_path, "clean").review(_REQUEST)

    asyncio.run(run())


def test_registered_acp_rule_runs_through_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    analyzer = builtin_analyzers()[0]
    analyzer.bundles.register(
        PromptReviewRule("ownership", _GUIDELINE, _agent(tmp_path, "finding"))
    )
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "app.py").write_bytes(_REQUEST.source.content)
    assert main(["--root", str(tmp_path), "--all"], registry) == 1
    assert "review.ownership: Shared mutable state" in capsys.readouterr().out
    assert (tmp_path / "app.py").read_bytes() == _REQUEST.source.content


@pytest.mark.parametrize("mode", ["finding", "empty-chat", "duplicate"])
def test_tool_submissions_are_authoritative_without_final_json(tmp_path: Path, mode: str) -> None:
    result = _agent(tmp_path, mode).review(_REQUEST)
    assert len(result.findings) == 1
    assert result.summary == "Reviewed ownership"


def test_many_findings_do_not_require_a_large_final_response(tmp_path: Path) -> None:
    result = _agent(tmp_path, "many").review(_REQUEST)
    assert len(result.findings) == 100
    assert result.findings[-1].message == "Evidence 99"


def test_clean_review_requires_explicit_tool_completion(tmp_path: Path) -> None:
    result = _agent(tmp_path, "clean").review(_REQUEST)
    assert result.status == "complete"
    assert result.findings == ()


def test_async_cancellation_reaps_agent(tmp_path: Path) -> None:
    async def run() -> None:
        task = asyncio.create_task(_agent(tmp_path, "hang").review_async(_REQUEST))
        async with asyncio.timeout(5.0):
            while not (tmp_path / "record.prompt").exists():
                await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    with pytest.raises(ProcessLookupError):
        os.kill(int((tmp_path / "record.pid").read_text()), 0)


@pytest.mark.parametrize("mode", ["incomplete", "no-finish"])
def test_incomplete_tool_review_fails_cli(tmp_path: Path, mode: str) -> None:
    analyzer = builtin_analyzers()[0]
    analyzer.bundles.register(PromptReviewRule("ownership", _GUIDELINE, _agent(tmp_path, mode)))
    registry = AnalyzerRegistry()
    registry.register(analyzer)
    (tmp_path / ".codeharness").mkdir(exist_ok=True)
    (tmp_path / ".codeharness/code-harness.json").write_text("{}")
    (tmp_path / "app.py").write_bytes(_REQUEST.source.content)
    assert main(["--root", str(tmp_path), "--all"], registry) == 2


def test_empty_executable_is_rejected() -> None:
    with pytest.raises(ValueError, match="executable"):
        AcpCommand("")


@pytest.mark.parametrize("timeout", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        AcpCommand("agent", timeout_seconds=timeout)


@pytest.mark.parametrize(("output_limit", "prompt_limit"), [(0, 1), (1, 0)])
def test_invalid_byte_limits_are_rejected(output_limit: int, prompt_limit: int) -> None:
    with pytest.raises(ValueError, match="byte limits"):
        AcpCommand("agent", output_limit=output_limit, prompt_limit=prompt_limit)


def test_timeout_kills_an_agent_that_ignores_termination(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="timed out"):
        _agent(tmp_path, "ignore-term", timeout=2.0).review(_REQUEST)
    with pytest.raises(ProcessLookupError):
        os.kill(int((tmp_path / "record.pid").read_text()), 0)
