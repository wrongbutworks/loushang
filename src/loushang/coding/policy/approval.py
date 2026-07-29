"""Coding approval payload projection over the shared Harness lifecycle."""

from __future__ import annotations

import shlex
from collections.abc import Mapping
from pathlib import Path

from loushang.harness.approval import (
    ApprovalDecision,
    ApprovalPayloadProjector,
    ApprovalRequest,
    ApprovalResolver,
    DenyApprovalResolver,
    HeadlessApprovalResolver,
    JsonApprovalPolicyRuleStore,
    MaybeAwaitable,
    approval_request_to_dict,
    resolve_approval,
)
from loushang.harness.approval import (
    InteractiveApprovalResolver as _InteractiveApprovalResolver,
)
from loushang.harness.diagnostics.export import redact_text
from loushang.harness.tools.workspace.policy import PolicyEnforcementError


def _coding_approval_payload(request: ApprovalRequest) -> Mapping[str, object]:
    projection = approval_request_to_dict(request)
    grant_summary = (
        request.session_grant.summary if request.session_grant is not None else None
    )
    return {
        **projection,
        "action": _approval_action(request),
        "risk": request.reason or "Tool call requires approval",
        "environment": "local",
        "grant_summary": grant_summary,
    }


def _approval_action(request: ApprovalRequest) -> str:
    command = request.arguments.get("command")
    if isinstance(command, str) and command.strip():
        return _approval_display_text(command)
    if isinstance(command, (tuple, list)) and command and all(
        isinstance(part, str) for part in command
    ):
        return _approval_display_text(shlex.join(command))
    path = request.arguments.get("path")
    if isinstance(path, str) and path.strip():
        return f"{request.tool_name} {_approval_display_text(path)}"
    return f"{request.tool_name} tool call"


def _approval_display_text(value: str) -> str:
    redacted = redact_text(value.strip())
    flattened = " ⏎ ".join(redacted.splitlines())
    safe = "".join(
        character if character.isprintable() else "�"
        for character in flattened
    )
    return safe[:2048]


class InteractiveApprovalResolver(_InteractiveApprovalResolver):
    """Preserve Coding's approval panel payload while sharing lifecycle code."""

    def __init__(self, *, fallback: ApprovalResolver, timeout_seconds: float | None = None):
        super().__init__(
            fallback=fallback,
            timeout_seconds=timeout_seconds,
            payload_projector=_coding_approval_payload,
        )


def configure_persistent_approval_policy(
    resolver: ApprovalResolver | None,
    settings_manager: object | None,
) -> None:
    """Bind project/user Policy stores without leaking Coding paths to Harness."""

    setter = getattr(resolver, "set_policy_stores", None)
    if not callable(setter) or settings_manager is None:
        return
    project_base = getattr(settings_manager, "project_base_dir", None)
    global_base = getattr(settings_manager, "global_base_dir", None)
    stores = {}
    if isinstance(project_base, Path):
        stores["project"] = JsonApprovalPolicyRuleStore(
            "project",
            project_base / "approval-policy.json",
        )
    if isinstance(global_base, Path):
        stores["user"] = JsonApprovalPolicyRuleStore(
            "user",
            global_base / "approval-policy.json",
        )
    setter(stores)


__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalResolver",
    "DenyApprovalResolver",
    "HeadlessApprovalResolver",
    "InteractiveApprovalResolver",
    "MaybeAwaitable",
    "ApprovalPayloadProjector",
    "configure_persistent_approval_policy",
    "PolicyEnforcementError",
    "approval_request_to_dict",
    "resolve_approval",
]
