"""Coding approval payload projection over the shared Harness lifecycle."""

from __future__ import annotations

from collections.abc import Mapping

from loushang.harness.approval import (
    ApprovalDecision,
    ApprovalPayloadProjector,
    ApprovalRequest,
    ApprovalResolver,
    DenyApprovalResolver,
    HeadlessApprovalResolver,
    MaybeAwaitable,
    approval_request_to_dict,
    resolve_approval,
)
from loushang.harness.approval import (
    InteractiveApprovalResolver as _InteractiveApprovalResolver,
)
from loushang.harness.tools.workspace.policy import PolicyEnforcementError


def _coding_approval_payload(request: ApprovalRequest) -> Mapping[str, object]:
    projection = approval_request_to_dict(request)
    return {
        **projection,
        "action": request.reason or f"Approve {request.tool_name} tool call",
        "risk": request.reason or "Tool call requires approval",
    }


class InteractiveApprovalResolver(_InteractiveApprovalResolver):
    """Preserve Coding's approval panel payload while sharing lifecycle code."""

    def __init__(self, *, fallback: ApprovalResolver, timeout_seconds: float | None = None):
        super().__init__(
            fallback=fallback,
            timeout_seconds=timeout_seconds,
            payload_projector=_coding_approval_payload,
        )


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalResolver",
    "DenyApprovalResolver",
    "HeadlessApprovalResolver",
    "InteractiveApprovalResolver",
    "MaybeAwaitable",
    "ApprovalPayloadProjector",
    "PolicyEnforcementError",
    "approval_request_to_dict",
    "resolve_approval",
]
