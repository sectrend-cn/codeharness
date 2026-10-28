"""Invoke configured ACP agents over stdio with bounded process and session lifetimes."""

import asyncio
import math
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from acp.schema import (
    ClientCapabilities,
    Implementation,
    InitializeRequest,
    InitializeResponse,
    McpServerStdio,
    NewSessionRequest,
    NewSessionResponse,
    PromptRequest,
    PromptResponse,
    TextContentBlock,
)
from pydantic import ValidationError

from code_harness.diagnostics import AnalysisError
from code_harness.review.channel import AcpChannel
from code_harness.review.contracts import ReviewRequest, ReviewResult
from code_harness.review.prompt import ReviewPrompt
from code_harness.review.submission_models import ReviewScope
from code_harness.review.submissions import SubmissionStore
from code_harness.review.wire import InitializeCall, PromptCall, RpcResponse, SessionCall


@dataclass(frozen=True)
class AcpCommand:
    """Explicit argv and resource bounds; command execution never uses a shell."""

    executable: str
    arguments: tuple[str, ...] = ()
    timeout_seconds: float = 120.0
    output_limit: int = 4_000_000
    prompt_limit: int = 1_000_000

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValueError("ACP executable is required")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("ACP timeout must be finite and positive")
        if self.output_limit < 1 or self.prompt_limit < 1:
            raise ValueError("ACP byte limits must be positive")


@dataclass(frozen=True)
class AcpReviewAgent:
    """Own one isolated ACP session per review and fail closed on transport errors."""

    command: AcpCommand

    def review(self, request: ReviewRequest) -> ReviewResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.review_async(request))
        raise AnalysisError("Synchronous review cannot run inside an event loop; use review_async")

    async def review_async(self, request: ReviewRequest) -> ReviewResult:
        prompt = ReviewPrompt().render(request)
        if len(prompt.encode()) > self.command.prompt_limit:
            raise AnalysisError("Agent review prompt exceeds the configured byte limit")
        try:
            async with asyncio.timeout(self.command.timeout_seconds):
                return await self._invoke(request, prompt)
        except TimeoutError as error:
            raise AnalysisError("ACP agent review timed out") from error
        except (OSError, ValueError, ValidationError) as error:
            raise AnalysisError(f"ACP agent review failed: {error}") from error

    async def _invoke(self, request: ReviewRequest, prompt: str) -> ReviewResult:
        with TemporaryDirectory(prefix="code-harness-review-") as directory:
            SubmissionStore.create(Path(directory), ReviewScope.from_request(request))
            process = await asyncio.create_subprocess_exec(
                self.command.executable,
                *self.command.arguments,
                cwd=directory,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=self.command.output_limit,
                start_new_session=True,
            )
            try:
                if process.stdout is None or process.stdin is None:
                    raise AnalysisError("ACP agent has no stdio transport")
                channel = AcpChannel(process.stdout, process.stdin, self.command.output_limit)
                await self._session(channel, directory, prompt)
            finally:
                await self._stop(process)
            return SubmissionStore(Path(directory)).result()

    async def _session(self, channel: AcpChannel, directory: str, prompt: str) -> None:
        initialized = await channel.exchange(
            InitializeCall(
                id=1,
                params=InitializeRequest(
                    protocol_version=1,
                    client_capabilities=ClientCapabilities(),
                    client_info=Implementation(name="code-harness", version="0.1.0"),
                ),
            ),
            RpcResponse[InitializeResponse],
        )
        if initialized.protocol_version != 1:
            raise AnalysisError("ACP agent selected an unsupported protocol version")
        session = await channel.exchange(
            SessionCall(
                id=2,
                params=NewSessionRequest(
                    cwd=directory,
                    mcp_servers=[
                        McpServerStdio(
                            name="code-harness-review",
                            command=sys.executable,
                            args=["-m", "code_harness.review.mcp_server", directory],
                            env=[],
                        ),
                    ],
                ),
            ),
            RpcResponse[NewSessionResponse],
        )
        if not session.session_id.strip():
            raise AnalysisError("ACP agent returned an empty session identity")
        channel.session_id = session.session_id
        response = await channel.exchange(
            PromptCall(
                id=3,
                params=PromptRequest(
                    session_id=session.session_id,
                    prompt=[TextContentBlock(type="text", text=prompt)],
                ),
            ),
            RpcResponse[PromptResponse],
        )
        if response.stop_reason != "end_turn":
            raise AnalysisError(f"ACP review did not finish: {response.stop_reason}")
        channel.ensure_allowed()

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        if process.stdin is not None:
            process.stdin.close()
        self._signal(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(self._reap(process), timeout=2.0)
        except TimeoutError:
            self._signal(process, signal.SIGKILL)
            await self._reap(process)
        finally:
            self._signal(process, signal.SIGKILL)

    async def _reap(self, process: asyncio.subprocess.Process) -> None:
        await asyncio.gather(process.wait(), self._drain_output(process))

    async def _drain_output(self, process: asyncio.subprocess.Process) -> None:
        if process.stdout is not None:
            while await process.stdout.read(65536):
                pass

    def _signal(self, process: asyncio.subprocess.Process, action: signal.Signals) -> None:
        try:
            os.killpg(process.pid, action)
        except ProcessLookupError:
            pass
