from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from loushang.harness.approval import ApprovalResolver
from loushang.harness.authorization import (
    EffectiveExecutionProfile,
    ExecutionAuthorizationError,
    resolve_effective_execution_profile,
)
from loushang.harness.policy import ToolPolicySubject

from .policy import ToolPolicyEvaluator, enforce_tool_policy


@dataclass(frozen=True, slots=True)
class AuthorizedWorkspaceAction:
    tool_name: str
    arguments: Mapping[str, Any]
    cwd: str | None
    fingerprint: str
    execution_profile: EffectiveExecutionProfile | None = None


async def authorize_workspace_tool_action(
    policy_engine: ToolPolicyEvaluator | object | None,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None = None,
    policy_subject: ToolPolicySubject | None = None,
    approval_resolver: ApprovalResolver | None = None,
    tool_call_id: str | None = None,
    audit_sink: Any = None,
    execution_environment: object | None = None,
    execution_profile_ceiling: EffectiveExecutionProfile | None = None,
) -> AuthorizedWorkspaceAction:
    """Freeze one action before routing it through Policy and Approval."""

    frozen_arguments = _freeze_mapping(arguments)
    action = AuthorizedWorkspaceAction(
        tool_name=tool_name,
        arguments=frozen_arguments,
        cwd=cwd,
        fingerprint=_fingerprint(tool_name, frozen_arguments, cwd),
    )
    authorization = await enforce_tool_policy(
        policy_engine,
        tool_name=action.tool_name,
        arguments=action.arguments,
        cwd=action.cwd,
        policy_subject=policy_subject,
        approval_resolver=approval_resolver,
        tool_call_id=tool_call_id,
        audit_sink=audit_sink,
        execution_environment=execution_environment,
    )
    if execution_profile_ceiling is None:
        return action
    effective = resolve_effective_execution_profile(
        ceiling=execution_profile_ceiling,
        decision=authorization.decision,
        approval=authorization.approval,
        approval_action_id=authorization.approval_action_id,
    )
    _validate_path_authority(tool_name, frozen_arguments, effective)
    return AuthorizedWorkspaceAction(
        tool_name=action.tool_name,
        arguments=action.arguments,
        cwd=action.cwd,
        fingerprint=action.fingerprint,
        execution_profile=effective,
    )


def _fingerprint(
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
) -> str:
    payload = json.dumps(
        {
            "tool_name": tool_name,
            "arguments": _json_value(arguments),
            "cwd": cwd,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            str(key): _freeze_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _validate_path_authority(
    tool_name: str,
    arguments: Mapping[str, Any],
    profile: EffectiveExecutionProfile,
) -> None:
    path_value = arguments.get("path")
    if not isinstance(path_value, str):
        return
    path = Path(path_value).resolve(strict=False)
    if any(path == root or path.is_relative_to(root) for root in profile.denied_roots):
        raise ExecutionAuthorizationError(f"path is denied by execution profile: {path}")
    roots = (
        profile.readable_roots
        if tool_name == "read"
        else profile.writable_roots
        if tool_name in {"write", "edit"}
        else ()
    )
    if roots and any(path == root or path.is_relative_to(root) for root in roots):
        return
    if tool_name in {"read", "write", "edit"}:
        raise ExecutionAuthorizationError(
            f"path is outside the authorized {tool_name} roots: {path}"
        )


__all__ = ["AuthorizedWorkspaceAction", "authorize_workspace_tool_action"]
