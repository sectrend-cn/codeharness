"""A deterministic subprocess ACP peer for transport behavior tests."""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path
from typing import Literal

from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    InitializeResponse,
    McpServerStdio,
    NewSessionResponse,
    PromptResponse,
    SessionNotification,
    TextContentBlock,
)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

from code_harness.review.wire import (
    ErrorReply,
    InitializeCall,
    PermissionReply,
    PromptCall,
    RpcError,
    RpcResponse,
    SessionCall,
    SessionUpdate,
    WireModel,
)


class PermissionParams(BaseModel):
    sessionId: str = "test-session"


class PermissionCall(WireModel):
    id: str = "permission"
    method: Literal["session/request_permission"] = "session/request_permission"
    params: PermissionParams = PermissionParams()


class FixtureAgent:
    """Validate client requests and provide a selected protocol outcome."""

    def __init__(self, mode: str, record: Path) -> None:
        self.mode = mode
        self.record = record
        self.server: McpServerStdio | None = None

    def run(self) -> None:
        self.record.with_suffix(".pid").write_text(str(os.getpid()))
        self._initialize()
        self._session()
        raw = sys.stdin.buffer.readline()
        request = PromptCall.model_validate_json(raw)
        block = request.params.prompt[0]
        if not isinstance(block, TextContentBlock):
            raise ValueError("Expected a text review prompt")
        self.record.with_suffix(".prompt").write_text(block.text)
        self._review(request)

    def _initialize(self) -> None:
        request = InitializeCall.model_validate_json(sys.stdin.buffer.readline())
        self.record.write_text(request.model_dump_json(by_alias=True))
        version = 99 if self.mode == "version" else 1
        response = RpcResponse[InitializeResponse](
            id=request.id, result=InitializeResponse(protocol_version=version)
        )
        print(response.model_dump_json(by_alias=True), flush=True)

    def _session(self) -> None:
        request = SessionCall.model_validate_json(sys.stdin.buffer.readline())
        assert Path(request.params.cwd).is_absolute()
        assert request.params.cwd == os.getcwd()
        assert len(request.params.mcp_servers) == 1
        server = request.params.mcp_servers[0]
        assert isinstance(server, McpServerStdio)
        self.server = server
        self.record.with_suffix(".cwd").write_text(request.params.cwd)
        identity = "" if self.mode == "empty-session" else "test-session"
        response = RpcResponse[NewSessionResponse](
            id=request.id, result=NewSessionResponse(session_id=identity)
        )
        print(response.model_dump_json(by_alias=True), flush=True)

    def _review(self, request: PromptCall) -> None:
        if self.mode in {"hang", "ignore-term"}:
            self._hang()
        elif self.mode == "exit":
            return
        elif self.mode == "malformed":
            print("not JSON", flush=True)
            return
        elif self.mode == "rpc-error":
            failure = ErrorReply(
                id=request.id, error=RpcError(code=-32000, message="fixture failure")
            )
            print(failure.model_dump_json(), flush=True)
            return
        elif self.mode == "permission":
            self._permission()
        if self.mode in {
            "finding",
            "clean",
            "many",
            "incomplete",
            "no-finish",
            "duplicate",
            "empty-chat",
        }:
            asyncio.run(self._submit())
        self._stream_result()
        response = RpcResponse[PromptResponse](
            id=99 if self.mode == "wrong-id" else request.id,
            result=PromptResponse(
                stop_reason="cancelled" if self.mode == "cancelled" else "end_turn"
            ),
        )
        print(response.model_dump_json(by_alias=True), flush=True)

    def _hang(self) -> None:
        if self.mode == "ignore-term":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(30)

    def _permission(self) -> None:
        print(PermissionCall().model_dump_json(), flush=True)
        response = PermissionReply.model_validate_json(sys.stdin.buffer.readline())
        self.record.with_suffix(".permission").write_text(response.result.outcome.outcome)

    def _stream_result(self) -> None:
        if self.mode in {"empty", "empty-chat"}:
            return
        text = "Submitted review through tools."
        if self.mode == "oversized":
            text = "x" * 10000
        session_id = "other-session" if self.mode == "wrong-session" else "test-session"
        thought = SessionUpdate(
            method="session/update",
            params=SessionNotification(
                session_id=session_id,
                update=AgentThoughtChunk(
                    session_update="agent_thought_chunk",
                    content=TextContentBlock(type="text", text="not a result"),
                ),
            ),
        )
        print(thought.model_dump_json(by_alias=True), flush=True)
        for chunk in (text[: len(text) // 2], text[len(text) // 2 :]):
            update = SessionUpdate(
                method="session/update",
                params=SessionNotification(
                    session_id=session_id,
                    update=AgentMessageChunk(
                        session_update="agent_message_chunk",
                        content=TextContentBlock(type="text", text=chunk),
                    ),
                ),
            )
            print(update.model_dump_json(by_alias=True), flush=True)

    async def _submit(self) -> None:
        assert self.server is not None
        parameters = StdioServerParameters(command=self.server.command, args=self.server.args)
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                available = await client.list_tools()
                assert {tool.name for tool in available.tools} == {
                    "submit_finding",
                    "finish_review",
                }
                count = 0 if self.mode == "clean" else 100 if self.mode == "many" else 1
                await self._findings(client, count)
                if self.mode == "no-finish":
                    return
                completion = await client.call_tool(
                    "finish_review",
                    arguments={
                        "status": "incomplete" if self.mode == "incomplete" else "complete",
                        "summary": "Reviewed ownership",
                        "expected_findings": count,
                    },
                )
                assert not completion.isError

    async def _findings(self, client: ClientSession, count: int) -> None:
        for index in range(count):
            result = await client.call_tool(
                "submit_finding",
                arguments={
                    "submission_id": f"finding-{index}",
                    "line": 1,
                    "column": 1,
                    "message": "Shared mutable state" if index == 0 else f"Evidence {index}",
                },
            )
            assert not result.isError
            assert "Shared mutable state" not in result.model_dump_json()
            assert len(result.model_dump_json()) < 1000
        if self.mode == "duplicate":
            retry = await client.call_tool(
                "submit_finding",
                arguments={
                    "submission_id": "finding-0",
                    "line": 1,
                    "column": 1,
                    "message": "Shared mutable state",
                },
            )
            assert not retry.isError


if __name__ == "__main__":
    FixtureAgent(sys.argv[1], Path(sys.argv[2])).run()
