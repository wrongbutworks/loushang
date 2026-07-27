from __future__ import annotations

import inspect
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from loushang.harness.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResolver,
    ensure_approval_action_id,
    resolve_approval,
)
from loushang.harness.policy import (
    MaybeAwaitable,
    PolicyDecision,
    PolicyEvaluationError,
    PolicyEvaluator,
    ToolPolicySubject,
    build_tool_policy_subject,
    evaluate_policy,
    executable_search_path_from_env,
    normalize_command_subject,
)


class PolicyDecisionLike(Protocol):
    @property
    def disposition(self) -> Literal["allow", "deny", "ask"]: ...

    @property
    def reason(self) -> str | None: ...

    @property
    def code(self) -> str | None: ...


class ToolPolicyEvaluator(Protocol):
    def evaluate(
        self, subject: ToolPolicySubject, /
    ) -> MaybeAwaitable[PolicyDecision | None]: ...


class PolicyEnforcementError(PermissionError):
    def __init__(self, message: str, *, tool_result_details: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.tool_result_details = dict(tool_result_details)


@dataclass(frozen=True, slots=True)
class ToolPolicyAuthorization:
    decision: PolicyDecision
    approval: ApprovalDecision | None = None
    approval_action_id: str | None = None


async def enforce_tool_policy(
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
) -> ToolPolicyAuthorization:
    if policy_engine is None:
        return ToolPolicyAuthorization(PolicyDecision.allow())
    execution_subject = build_tool_policy_subject(
        tool_name=tool_name,
        arguments=arguments,
        cwd=cwd,
    )
    environment_snapshot = _snapshot_execution_environment(execution_environment)
    _validate_execution_arguments(execution_subject)
    if policy_subject is not None:
        _validate_policy_subject_matches_execution(
            policy_subject,
            execution_subject,
            execution_environment=environment_snapshot,
        )
    subject = policy_subject or execution_subject
    tool_name = subject.tool_name
    arguments = subject.arguments
    cwd = subject.cwd
    decision = await _evaluate_tool_policy(
        policy_engine,
        tool_name=tool_name,
        arguments=arguments,
        cwd=cwd,
        subject=subject,
    )
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
        return ToolPolicyAuthorization(decision)
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
        request = ensure_approval_action_id(
            ApprovalRequest(
                tool_name=tool_name,
                arguments=arguments,
                cwd=cwd,
                reason=decision.reason,
                policy_code=decision.code,
                policy_decision=decision,
            )
        )
        action_id = request.action_id
        assert action_id is not None
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
            return ToolPolicyAuthorization(
                decision,
                approval=approval,
                approval_action_id=action_id,
            )
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


async def _evaluate_tool_policy(
    policy_engine: ToolPolicyEvaluator | object,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
    subject: ToolPolicySubject,
) -> PolicyDecision:
    evaluate = get_policy_method(policy_engine, "evaluate")
    if callable(evaluate):
        decision = await evaluate_policy(
            cast(PolicyEvaluator, policy_engine),
            subject,
        )
        if decision is not None:
            return decision
        legacy_evaluate = get_policy_method(policy_engine, "evaluate_tool_call")
        if not callable(legacy_evaluate):
            return PolicyDecision.allow()
    else:
        legacy_evaluate = get_policy_method(policy_engine, "evaluate_tool_call")

    # Compatibility evaluators keep their established call shape during the
    # transition. When a dual-protocol adapter abstains through the new
    # contract, its legacy result remains authoritative.
    if callable(legacy_evaluate):
        return await _evaluate_legacy_tool_policy(
            policy_engine,
            legacy_evaluate=legacy_evaluate,
            tool_name=tool_name,
            arguments=arguments,
            cwd=cwd,
        )

    if not callable(evaluate):
        raise PolicyEvaluationError(
            f"Policy evaluator {type(policy_engine).__name__} has no supported evaluate method"
        )
    return PolicyDecision.allow()


def _validate_execution_arguments(execution: ToolPolicySubject) -> None:
    if execution.tool_name != "bash" or "cwd" not in execution.arguments:
        return
    argument_cwd = execution.arguments["cwd"]
    if argument_cwd is not None and not isinstance(argument_cwd, str):
        raise PolicyEvaluationError(
            "Bash execution argument cwd must be a string or None"
        )
    if argument_cwd != execution.cwd:
        raise PolicyEvaluationError(
            "Bash execution argument cwd does not match the execution cwd"
        )


def _validate_policy_subject_matches_execution(
    subject: ToolPolicySubject,
    execution: ToolPolicySubject,
    *,
    execution_environment: tuple[tuple[str, str], ...] | None,
) -> None:
    mismatches = []
    if subject.tool_name != execution.tool_name:
        mismatches.append("tool_name")
    if subject.arguments != execution.arguments:
        mismatches.append("arguments")
    if subject.cwd != execution.cwd:
        mismatches.append("cwd")
    if subject.paths != execution.paths:
        mismatches.append("paths")
    argument_command = execution.arguments.get("command")
    if argument_command is None:
        if subject.command is not None:
            mismatches.append("command")
    elif subject.command is None:
        mismatches.append("command")
    else:
        stdin = execution.arguments.get("stdin")
        normalized_stdin = stdin if isinstance(stdin, str) else None
        normalization_environment = (
            execution_environment
            if execution_environment is not None
            else execution.arguments.get("env", ())
        )
        executable_search_path = executable_search_path_from_env(
            normalization_environment,
            default=os.defpath if execution_environment is not None else None,
        )
        expected_command = None
        command_matches_argument = True
        if isinstance(argument_command, str):
            expected_command = normalize_command_subject(
                subject.command.command,
                cwd=execution.cwd,
                assume_shell=True,
                stdin=normalized_stdin,
                executable_search_path=executable_search_path,
                environment_overrides=normalization_environment,
                environment_is_complete=execution_environment is not None,
            )
            command_matches_argument = (
                expected_command.shell_payload == argument_command
            )
        elif isinstance(argument_command, (list, tuple)) and all(
            isinstance(part, str) for part in argument_command
        ):
            expected_command = normalize_command_subject(
                tuple(argument_command),
                cwd=execution.cwd,
                stdin=normalized_stdin,
                executable_search_path=executable_search_path,
                environment_overrides=normalization_environment,
                environment_is_complete=execution_environment is not None,
            )
        if subject.command != expected_command or not command_matches_argument:
            mismatches.append("command")
    if mismatches:
        raise PolicyEvaluationError(
            "Policy subject does not match execution fields: " + ", ".join(mismatches)
        )


def _snapshot_execution_environment(
    environment: object | None,
) -> tuple[tuple[str, str], ...] | None:
    if environment is None:
        return None
    values = environment.items() if isinstance(environment, Mapping) else environment
    if isinstance(values, str) or not isinstance(values, Iterable):
        raise TypeError("execution_environment must contain 2-item string pairs")
    snapshot: list[tuple[str, str]] = []
    for item in values:
        if isinstance(item, str) or not isinstance(item, (list, tuple)):
            raise TypeError("execution_environment must contain 2-item string pairs")
        pair = tuple(item)
        if len(pair) != 2 or not all(isinstance(part, str) for part in pair):
            raise TypeError("execution_environment must contain 2-item string pairs")
        snapshot.append((pair[0], pair[1]))
    return tuple(snapshot)


def get_policy_method(policy_engine: object, name: str) -> object:
    try:
        return getattr(policy_engine, name, None)
    except Exception as exc:
        raise PolicyEvaluationError(
            f"Policy evaluator {type(policy_engine).__name__} failed while "
            f"accessing {name}: {exc}"
        ) from exc


async def _evaluate_legacy_tool_policy(
    policy_engine: object,
    *,
    legacy_evaluate: Any,
    tool_name: str,
    arguments: Mapping[str, Any],
    cwd: str | None,
) -> PolicyDecision:
    return await evaluate_legacy_policy_method(
        policy_engine,
        "evaluate_tool_call",
        method=legacy_evaluate,
        tool_name=tool_name,
        arguments=arguments,
        cwd=cwd,
    )


async def evaluate_legacy_policy_method(
    policy_engine: object,
    method_name: str,
    *,
    method: object | None = None,
    **kwargs: object,
) -> PolicyDecision:
    resolved_method = (
        method if method is not None else get_policy_method(policy_engine, method_name)
    )
    if not callable(resolved_method):
        raise PolicyEvaluationError(
            f"Policy evaluator {type(policy_engine).__name__} has no callable "
            f"{method_name} method"
        )
    try:
        result = resolved_method(**kwargs)
        if inspect.isawaitable(result):
            result = await result
    except PolicyEvaluationError:
        raise
    except Exception as exc:
        raise PolicyEvaluationError(
            f"Policy evaluator {type(policy_engine).__name__} failed: {exc}"
        ) from exc
    return _coerce_legacy_decision(result, evaluator=policy_engine)


def _coerce_legacy_decision(
    result: object,
    *,
    evaluator: object,
) -> PolicyDecision:
    if isinstance(result, PolicyDecision):
        try:
            result.__post_init__()
        except (TypeError, ValueError) as exc:
            raise PolicyEvaluationError(
                f"Policy evaluator {type(evaluator).__name__} returned an invalid "
                f"PolicyDecision: {exc}"
            ) from exc
        return result
    try:
        disposition = getattr(result, "disposition", None)
        reason = getattr(result, "reason", None)
        code = getattr(result, "code", None)
    except Exception as exc:
        raise PolicyEvaluationError(
            f"Policy evaluator {type(evaluator).__name__} returned an invalid "
            f"decision: {exc}"
        ) from exc
    if disposition not in {"allow", "deny", "ask"}:
        raise PolicyEvaluationError(
            f"Policy evaluator {type(evaluator).__name__} returned an invalid decision"
        )
    if reason is not None and not isinstance(reason, str):
        raise PolicyEvaluationError(
            f"Policy evaluator {type(evaluator).__name__} returned a non-string reason"
        )
    if code is not None and not isinstance(code, str):
        raise PolicyEvaluationError(
            f"Policy evaluator {type(evaluator).__name__} returned a non-string code"
        )
    return PolicyDecision(disposition=disposition, reason=reason, code=code)


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
        elif (
            key == "command"
            and isinstance(value, (list, tuple))
            and all(isinstance(part, str) for part in value)
        ):
            details[key] = tuple(value)
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
        elif (
            key == "command"
            and isinstance(value, (list, tuple))
            and all(isinstance(part, str) for part in value)
        ):
            details[key] = tuple(value)
    return details


async def _emit_policy_audit_event(audit_sink: Any, event: Mapping[str, Any]) -> None:
    if audit_sink is None:
        return
    result = audit_sink(dict(event))
    if inspect.isawaitable(result):
        await result
