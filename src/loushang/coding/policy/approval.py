from __future__ import annotations

import inspect
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

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
