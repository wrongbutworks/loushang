from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loushang.coding.policy import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResolver,
    PolicyDecision,
    PolicyEnforcementError,
    PolicyEngine,
    resolve_approval,
)


async def enforce_tool_policy(
    policy_engine: PolicyEngine | None,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None = None,
    approval_resolver: ApprovalResolver | None = None,
) -> None:
    if policy_engine is None:
        return
    evaluate_tool_call = getattr(policy_engine, "evaluate_tool_call", None)
    if not callable(evaluate_tool_call):
        return
    decision = evaluate_tool_call(tool_name=tool_name, arguments=arguments, cwd=cwd)
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
        approval = await resolve_approval(
            approval_resolver,
            ApprovalRequest(
                tool_name=tool_name,
                arguments=arguments,
                cwd=cwd,
                reason=decision.reason,
                policy_code=decision.code,
                policy_decision=decision,
            ),
        )
        if approval.disposition == "allow":
            return
        message = approval.reason or decision.reason or f"Tool {tool_name} requires approval"
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
            ),
        )


def _policy_error_details(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
    decision: PolicyDecision,
    approval_required: bool,
    approval: ApprovalDecision | None = None,
    approval_reason: str | None = None,
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
    for key in ("path", "file_path", "command"):
        value = arguments.get(key)
        if isinstance(value, str):
            details[key] = value
    return details
