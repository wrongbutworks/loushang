from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loushang.harness.approval import (
    ApprovalBroker,
    ApprovalDecision,
    ApprovalPresenter,
    ApprovalRequest,
    ApprovalResolver,
    DenyApprovalResolver,
    HeadlessApprovalResolver,
    MaybeAwaitable,
    approval_request_to_dict,
    resolve_approval,
)
from loushang.harness.tools.workspace.policy import PolicyEnforcementError

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


@dataclass
class InteractiveApprovalResolver:
    fallback: ApprovalResolver
    timeout_seconds: float | None = None
    _broker: ApprovalBroker = field(init=False, repr=False)
    _request_presenter: Callable[[dict[str, object]], Awaitable[None] | None] | None = (
        field(default=None, init=False, repr=False)
    )
    _request_dismisser: Callable[[str], Awaitable[None] | None] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _session_open: bool = field(default=True, init=False, repr=False)
    _session_close_reason: str = field(
        default="Session closed before approval was resolved",
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self._broker = ApprovalBroker(
            fallback=self.fallback,
            timeout_seconds=self.timeout_seconds,
        )

    def set_request_presenter(
        self,
        presenter: Callable[[dict[str, object]], Awaitable[None] | None] | None,
        *,
        dismisser: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> None:
        if presenter is None and dismisser is not None:
            raise ValueError("dismisser requires a request presenter")
        self._broker.set_presenter(
            _CodingApprovalPresenter(presenter, dismisser)
            if presenter is not None
            else None
        )
        self._request_presenter = presenter
        self._request_dismisser = dismisser

    async def resolve(self, request: ApprovalRequest) -> ApprovalDecision:
        if not self._session_open:
            return ApprovalDecision.deny(self._session_close_reason)
        return await self._broker.resolve(request)

    def open_session(self) -> None:
        self._session_open = True

    async def handle_result(
        self, action_id: str, *, approved: bool, reason: str | None = None
    ) -> bool:
        return self._broker.resolve_request(
            action_id,
            ApprovalDecision.allow() if approved else ApprovalDecision.deny(reason),
        )

    def close_session(
        self,
        reason: str = "Session closed before approval was resolved",
    ) -> int:
        self._session_open = False
        self._session_close_reason = reason
        return self._broker.cancel_all(ApprovalDecision.deny(reason))

    def dispose(
        self, reason: str = "Session closed before approval was resolved"
    ) -> int:
        decision = ApprovalDecision.deny(reason)
        self._session_open = False
        self._session_close_reason = reason
        self._broker.set_presenter(None)
        self._request_presenter = None
        self._request_dismisser = None
        return self._broker.dispose(decision)


@dataclass(frozen=True)
class _CodingApprovalPresenter(ApprovalPresenter):
    callback: Callable[[dict[str, object]], Awaitable[None] | None]
    dismiss_callback: Callable[[str], Awaitable[None] | None] | None = None

    async def present(self, request: ApprovalRequest) -> None:
        projection = approval_request_to_dict(request)
        payload: dict[str, object] = {
            "action_id": projection["action_id"],
            "tool_name": projection["tool_name"],
            "action": request.reason or f"Approve {request.tool_name} tool call",
            "risk": request.reason or "Tool call requires approval",
            "cwd": projection["cwd"],
            "arguments": projection["arguments"],
            "policy_code": projection["policy_code"],
        }
        result = self.callback(payload)
        if inspect.isawaitable(result):
            await result

    def dismiss(self, request: ApprovalRequest) -> Awaitable[None] | None:
        if self.dismiss_callback is None or request.action_id is None:
            return None
        return self.dismiss_callback(request.action_id)
