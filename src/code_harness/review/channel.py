"""Bounded sequential ACP exchanges and read-only inbound request handling."""

import asyncio

from acp.schema import (
    AgentMessageChunk,
    DeniedOutcome,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    RequestPermissionResponse,
    TextContentBlock,
)

from code_harness.diagnostics import AnalysisError
from code_harness.review.wire import (
    ErrorReply,
    InitializeCall,
    MessageHeader,
    PermissionReply,
    PromptCall,
    RpcError,
    RpcResponse,
    SessionCall,
    SessionUpdate,
)


class AcpChannel:
    """Own framing, response correlation, and session notification validation."""

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, output_limit: int
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._remaining = output_limit
        self.session_id: str | None = None
        self.permission_denied = False

    async def exchange[ResultT: (InitializeResponse, NewSessionResponse, PromptResponse)](
        self,
        request: InitializeCall | SessionCall | PromptCall,
        response_type: type[RpcResponse[ResultT]],
    ) -> ResultT:
        self._writer.write(
            (request.model_dump_json(by_alias=True, exclude_none=True) + "\n").encode()
        )
        await self._writer.drain()
        while True:
            raw = await self._read()
            header = MessageHeader.model_validate_json(raw)
            if header.method is not None:
                await self._incoming(header, raw)
                continue
            if header.id != request.id:
                raise AnalysisError("ACP response ID does not match the pending request")
            if header.error is not None:
                raise AnalysisError(
                    f"ACP request failed ({header.error.code}): {header.error.message}"
                )
            return response_type.model_validate_json(raw).result

    async def _read(self) -> bytes:
        raw = await self._reader.readline()
        if not raw or not raw.endswith(b"\n"):
            raise AnalysisError("ACP agent closed the stream before a complete response")
        self._remaining -= len(raw)
        if self._remaining < 0:
            raise AnalysisError("ACP agent exceeded the output limit")
        return raw

    async def _incoming(self, header: MessageHeader, raw: bytes) -> None:
        if header.id is not None:
            await self._reject_request(header)
        elif header.method == "session/update":
            self._update(SessionUpdate.model_validate_json(raw))

    async def _reject_request(self, header: MessageHeader) -> None:
        if header.id is None:
            raise AnalysisError("ACP request has no identity")
        self.permission_denied = True
        if header.method == "session/request_permission":
            reply = PermissionReply(
                id=header.id,
                result=RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled")),
            )
            data = reply.model_dump_json(by_alias=True, exclude_none=True)
        else:
            failure = ErrorReply(
                id=header.id,
                error=RpcError(
                    code=-32601, message="Review client does not provide tools or filesystem access"
                ),
            )
            data = failure.model_dump_json()
        self._writer.write((data + "\n").encode())
        await self._writer.drain()

    def _update(self, notification: SessionUpdate) -> None:
        if self.session_id is None or notification.params.session_id != self.session_id:
            raise AnalysisError("ACP update belongs to an unexpected session")
        update = notification.params.update
        if isinstance(update, AgentMessageChunk):
            if not isinstance(update.content, TextContentBlock):
                raise AnalysisError("ACP reviewer returned non-text review content")
            return

    def ensure_allowed(self) -> None:
        if self.permission_denied:
            raise AnalysisError("Agent review requested unavailable permissions or tools")
