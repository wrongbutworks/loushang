from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, Literal, Protocol
from uuid import uuid4

from loushang.harness.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResolver,
    resolve_approval,
)


class PolicyDecisionLike(Protocol):
    disposition: Literal["allow", "deny", "ask"]
    reason: str | None
    code: str | None


class ToolPolicyEvaluator(Protocol):
    def evaluate_tool_call(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        cwd: str | None = None,
    ) -> PolicyDecisionLike: ...


class PolicyEnforcementError(PermissionError):
    def __init__(self, message: str, *, tool_result_details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.tool_result_details = dict(tool_result_details)


async def enforce_tool_policy(
    policy_engine: ToolPolicyEvaluator | object | None,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None = None,
    approval_resolver: ApprovalResolver | None = None,
    tool_call_id: str | None = None,
    audit_sink: Any = None,
) -> None:
    if policy_engine is None:
        return
    evaluate_tool_call = getattr(policy_engine, "evaluate_tool_call", None)
    if not callable(evaluate_tool_call):
        return
    decision = evaluate_tool_call(tool_name=tool_name, arguments=arguments, cwd=cwd)
    await _emit_policy_audit_event(
        audit_sink,
        {
            "type": "tool_policy_evaluated",
            **_policy_audit_details(
                tool_name=tool_name,
                arguments=arguments,
                cwd=cwd,
                decision=decision,
                approval_required=decision.disposition == "ask",
                tool_call_id=tool_call_id,
            ),
        },
    )
    if decision.disposition == "allow":
        return
    if decision.disposition == "deny":
        message = decision.reason or f"Tool {tool_name} denied by policy"
        raise PolicyEnforcementError(
            message,
            tool_result_details=_policy_error_details(
                tool_name=tool_name,
                arguments=arguments,
                cwd=cwd,
                decision=decision,
                approval_required=False,
            ),
        )
    if decision.disposition == "ask":
        action_id = f"policy-{uuid4().hex}"
        request = ApprovalRequest(
            tool_name=tool_name,
            arguments=arguments,
            cwd=cwd,
            reason=decision.reason,
            policy_code=decision.code,
            policy_decision=decision,
            action_id=action_id,
        )
        await _emit_policy_audit_event(
            audit_sink,
            {
                "type": "tool_approval_requested",
                **_approval_audit_details(
                    tool_name=tool_name,
                    arguments=arguments,
                    cwd=cwd,
                    decision=decision,
                    action_id=action_id,
                    tool_call_id=tool_call_id,
                ),
            },
        )
        approval = await resolve_approval(
            approval_resolver,
            request,
        )
        await _emit_policy_audit_event(
            audit_sink,
            {
                "type": "tool_approval_resolved",
                **_approval_audit_details(
                    tool_name=tool_name,
                    arguments=arguments,
                    cwd=cwd,
                    decision=decision,
                    action_id=action_id,
                    tool_call_id=tool_call_id,
                    approval=approval,
                ),
            },
        )
        if approval.disposition == "allow":
            return
        message = (
            approval.reason or decision.reason or f"Tool {tool_name} requires approval"
        )
        raise PolicyEnforcementError(
            message,
            tool_result_details=_policy_error_details(
                tool_name=tool_name,
                arguments=arguments,
                cwd=cwd,
                decision=decision,
                approval_required=True,
                approval=approval,
                approval_reason=message,
                approval_action_id=request.action_id,
            ),
        )


def _policy_error_details(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
    decision: PolicyDecisionLike,
    approval_required: bool,
    approval: ApprovalDecision | None = None,
    approval_reason: str | None = None,
    approval_action_id: str | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "tool_name": tool_name,
        "policy_disposition": decision.disposition,
        "approval_required": approval_required,
        "argument_keys": sorted(str(key) for key in arguments.keys()),
    }
    if cwd is not None:
        details["cwd"] = cwd
    if decision.code is not None:
        details["policy_code"] = decision.code
    if decision.reason is not None:
        details["policy_reason"] = decision.reason
    if approval is not None:
        details["approval_decision"] = approval.disposition
    if approval_reason is not None:
        details["approval_reason"] = approval_reason
    if approval_action_id is not None:
        details["approval_action_id"] = approval_action_id
    for key in ("path", "file_path", "command"):
        value = arguments.get(key)
        if isinstance(value, str):
            details[key] = value
    return details


def _policy_audit_details(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
    decision: PolicyDecisionLike,
    approval_required: bool,
    tool_call_id: str | None,
) -> dict[str, Any]:
    details = _policy_error_details(
        tool_name=tool_name,
        arguments=arguments,
        cwd=cwd,
        decision=decision,
        approval_required=approval_required,
    )
    if tool_call_id is not None:
        details["tool_call_id"] = tool_call_id
    return details


def _approval_audit_details(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
    decision: PolicyDecisionLike,
    action_id: str,
    tool_call_id: str | None,
    approval: ApprovalDecision | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "tool_name": tool_name,
        "action_id": action_id,
        "argument_keys": sorted(str(key) for key in arguments.keys()),
    }
    if tool_call_id is not None:
        details["tool_call_id"] = tool_call_id
    if cwd is not None:
        details["cwd"] = cwd
    if decision.code is not None:
        details["policy_code"] = decision.code
    if decision.reason is not None:
        details["policy_reason"] = decision.reason
    if approval is not None:
        details["approval_decision"] = approval.disposition
        if approval.reason is not None:
            details["approval_reason"] = approval.reason
    for key in ("path", "file_path", "command"):
        value = arguments.get(key)
        if isinstance(value, str):
            details[key] = value
    return details


async def _emit_policy_audit_event(audit_sink: Any, event: Mapping[str, Any]) -> None:
    if audit_sink is None:
        return
    result = audit_sink(dict(event))
    if inspect.isawaitable(result):
        await result
