from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

from loushang.harness.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResolver,
    DenyApprovalResolver,
    HeadlessApprovalResolver,
    MaybeAwaitable,
    resolve_approval,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalResolver",
    "DenyApprovalResolver",
    "HeadlessApprovalResolver",
    "InteractiveApprovalResolver",
    "MaybeAwaitable",
    "PolicyEnforcementError",
    "resolve_approval",
]


class PolicyEnforcementError(PermissionError):
    def __init__(self, message: str, *, tool_result_details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.tool_result_details = dict(tool_result_details)


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


async def _resolve(resolver: ApprovalResolver, request: ApprovalRequest) -> ApprovalDecision:
    result = resolver.resolve(request)
    if inspect.isawaitable(result):
        return await result
    return result
