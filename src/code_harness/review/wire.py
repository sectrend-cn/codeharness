"""Typed JSON-RPC envelopes around the ACP SDK's canonical wire schemas."""

from typing import Literal

from acp.schema import (
    InitializeRequest,
    InitializeResponse,
    NewSessionRequest,
    NewSessionResponse,
    PromptRequest,
    PromptResponse,
    RequestPermissionResponse,
    SessionNotification,
)
from pydantic import BaseModel, ConfigDict


class WireModel(BaseModel):
    """Ignore protocol extension fields at ingress while retaining declared contracts."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    jsonrpc: Literal["2.0"] = "2.0"


class InitializeCall(WireModel):
    id: int
    method: Literal["initialize"] = "initialize"
    params: InitializeRequest


class SessionCall(WireModel):
    id: int
    method: Literal["session/new"] = "session/new"
    params: NewSessionRequest


class PromptCall(WireModel):
    id: int
    method: Literal["session/prompt"] = "session/prompt"
    params: PromptRequest


class RpcResponse[ResultT: (InitializeResponse, NewSessionResponse, PromptResponse)](WireModel):
    """Decode the expected result directly from the transport without generic JSON carriers."""

    id: int
    result: ResultT


class RpcError(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    code: int
    message: str


class MessageHeader(BaseModel):
    """Classify an untrusted frame before decoding its method-specific schema."""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)
    jsonrpc: Literal["2.0"]
    id: int | str | None = None
    method: str | None = None
    error: RpcError | None = None


class SessionUpdate(WireModel):
    method: Literal["session/update"]
    params: SessionNotification


class PermissionReply(WireModel):
    id: int | str
    result: RequestPermissionResponse


class ErrorReply(WireModel):
    id: int | str
    error: RpcError
