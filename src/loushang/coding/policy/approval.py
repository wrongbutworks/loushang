from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal, Protocol, TypeVar
from uuid import uuid4

from loushang.coding.policy.types import PolicyDecision


T = TypeVar("T")
MaybeAwaitable = T | Awaitable[T]


@dataclass(frozen=True)
class ApprovalRequest:
    tool_name: str
    arguments: Mapping[str, Any]
    cwd: str | None = None
    reason: str | None = None
    policy_code: str | None = None
    policy_decision: PolicyDecision | None = None
    action_id: str | None = None


@dataclass(frozen=True)
class ApprovalDecision:
    disposition: Literal["allow", "deny"]
    reason: str | None = None

    @classmethod
    def allow(cls) -> "ApprovalDecision":
        return cls(disposition="allow")

    @classmethod
    def deny(cls, reason: str | None = None) -> "ApprovalDecision":
        return cls(disposition="deny", reason=reason)


class ApprovalResolver(Protocol):
    def resolve(self, request: ApprovalRequest) -> MaybeAwaitable[ApprovalDecision]: ...


class PolicyEnforcementError(PermissionError):
    def __init__(self, message: str, *, tool_result_details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.tool_result_details = dict(tool_result_details)


@dataclass(frozen=True)
class DenyApprovalResolver:
    def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision.deny(request.reason or f"Tool {request.tool_name} requires approval")


@dataclass
class InteractiveApprovalResolver:
    fallback: ApprovalResolver
    _pending_approvals: dict[str, asyncio.Future[ApprovalDecision]] = field(default_factory=dict, init=False, repr=False)
    _request_presenter: Callable[[dict[str, object]], Awaitable[None] | None] | None = field(default=None, init=False, repr=False)
    _request_counter: int = field(default=0, init=False, repr=False)

    def set_request_presenter(self, presenter: Callable[[dict[str, object]], Awaitable[None] | None] | None) -> None:
        self._request_presenter = presenter

    async def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        request_with_id = replace(
            request,
            action_id=request.action_id or self._next_action_id(),
        )
        self._pending_approvals[request_with_id.action_id] = future
        presented = await self._present_request(request_with_id)
        if not presented:
            self._pending_approvals.pop(request_with_id.action_id, None)
            return await _resolve(self.fallback, request_with_id)
        try:
            return await future
        finally:
            self._pending_approvals.pop(request_with_id.action_id, None)

    async def handle_result(self, action_id: str, *, approved: bool, reason: str | None = None) -> bool:
        future = self._pending_approvals.get(action_id)
        if future is None:
            return False
        if future.done():
            return False
        future.set_result(ApprovalDecision.allow() if approved else ApprovalDecision.deny(reason))
        return True

    async def _present_request(self, request: ApprovalRequest) -> bool:
        presenter = self._request_presenter
        if presenter is None:
            return False
        payload = {
            "action_id": request.action_id,
            "tool_name": request.tool_name,
            "action": request.reason or f"Approve {request.tool_name} tool call",
            "risk": request.reason or "Tool call requires approval",
            "cwd": request.cwd,
            "arguments": request.arguments,
            "policy_code": request.policy_code,
        }
        result = presenter(payload)
        if inspect.isawaitable(result):
            await result
        return True

    def _next_action_id(self) -> str:
        self._request_counter += 1
        return f"approval-{self._request_counter:04d}-{uuid4().hex}"


@dataclass(frozen=True)
class HeadlessApprovalResolver:
    mode: Literal["allow", "deny"] = "deny"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"allow", "deny"}:
            raise ValueError(f"Unsupported headless approval mode: {self.mode}")

    def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        if self.mode == "allow":
            return ApprovalDecision.allow()
        return ApprovalDecision.deny(self.reason or request.reason or f"Tool {request.tool_name} requires approval")


async def resolve_approval(
    resolver: ApprovalResolver | None,
    request: ApprovalRequest,
) -> ApprovalDecision:
    resolved = resolver or DenyApprovalResolver()
    result = resolved.resolve(request)
    if inspect.isawaitable(result):
        return await result
    return result


async def _resolve(resolver: ApprovalResolver, request: ApprovalRequest) -> ApprovalDecision:
    result = resolver.resolve(request)
    if inspect.isawaitable(result):
        return await result
    return result
