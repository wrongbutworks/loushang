from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from loushang.harness.policy import (
    CommandSubstringMatcher,
    ExactToolNameMatcher,
    IncompleteCommandMatcher,
    PathSubstringMatcher,
    PolicyDecision,
    PolicyRule,
    PolicySubject,
    RulePolicyEvaluator,
    build_tool_policy_subject,
    executable_search_path_from_env,
    normalize_command_subject,
)
from loushang.harness.workspace.exec import ExecRequest, materialize_exec_request

_DEFAULT_BLOCKED_SUBSTRINGS: tuple[str, ...] = (
    "rm -rf",
    "git reset --hard",
)
_DEFAULT_ASK_SUBSTRINGS: tuple[str, ...] = (
    "git push",
    "curl | sh",
    "curl|sh",
    "wget | sh",
    "wget|sh",
)


def _normalize_substrings(
    values: tuple[str, ...] | list[str],
    field_name: str,
    defaults: tuple[str, ...],
) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")

    normalized: list[str] = list(defaults)
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a sequence of strings")
        if value and value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _normalize_strings(
    values: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    return _normalize_substrings(values, field_name, ())


@dataclass(frozen=True)
class PolicyEngine:
    """Reusable workspace policy evaluator assembled from product rules."""

    rule_id_prefix: str = "workspace"
    blocked_substrings: tuple[str, ...] = field(
        default_factory=lambda: _DEFAULT_BLOCKED_SUBSTRINGS
    )
    ask_substrings: tuple[str, ...] = field(
        default_factory=lambda: _DEFAULT_ASK_SUBSTRINGS
    )
    blocked_tools: tuple[str, ...] = field(default_factory=tuple)
    ask_tools: tuple[str, ...] = field(default_factory=tuple)
    blocked_path_substrings: tuple[str, ...] = field(default_factory=tuple)
    ask_path_substrings: tuple[str, ...] = field(default_factory=tuple)
    _evaluator: RulePolicyEvaluator = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id_prefix, str) or not self.rule_id_prefix:
            raise ValueError("rule_id_prefix must be a non-empty string")
        object.__setattr__(
            self,
            "blocked_substrings",
            _normalize_substrings(
                self.blocked_substrings,
                "blocked_substrings",
                _DEFAULT_BLOCKED_SUBSTRINGS,
            ),
        )
        object.__setattr__(
            self,
            "ask_substrings",
            _normalize_substrings(
                self.ask_substrings,
                "ask_substrings",
                _DEFAULT_ASK_SUBSTRINGS,
            ),
        )
        object.__setattr__(
            self,
            "blocked_tools",
            _normalize_strings(self.blocked_tools, "blocked_tools"),
        )
        object.__setattr__(
            self,
            "ask_tools",
            _normalize_strings(self.ask_tools, "ask_tools"),
        )
        object.__setattr__(
            self,
            "blocked_path_substrings",
            _normalize_strings(
                self.blocked_path_substrings,
                "blocked_path_substrings",
            ),
        )
        object.__setattr__(
            self,
            "ask_path_substrings",
            _normalize_strings(
                self.ask_path_substrings,
                "ask_path_substrings",
            ),
        )
        object.__setattr__(self, "_evaluator", RulePolicyEvaluator(self._rules()))

    def evaluate(self, subject: PolicySubject, /) -> PolicyDecision:
        return self._evaluator.evaluate(subject) or PolicyDecision.allow()

    def evaluate_action(
        self,
        *,
        tool_name: str,
        exec_request: ExecRequest,
    ) -> PolicyDecision:
        del tool_name
        exec_request = materialize_exec_request(exec_request)
        execution_environment = exec_request.effective_environment
        assert execution_environment is not None
        executable_search_path = executable_search_path_from_env(
            execution_environment,
            default=os.defpath,
        )
        return self.evaluate(
            normalize_command_subject(
                exec_request.command,
                cwd=exec_request.cwd,
                stdin=exec_request.stdin,
                executable_search_path=executable_search_path,
                environment_overrides=execution_environment,
                environment_is_complete=True,
            )
        )

    def evaluate_tool_call(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        cwd: str | None = None,
    ) -> PolicyDecision:
        command = None
        if tool_name == "bash":
            raw_command = arguments.get("command")
            normalized_command = None
            if isinstance(raw_command, str):
                normalized_command = ("/bin/sh", "-lc", raw_command)
            elif (
                isinstance(raw_command, (list, tuple))
                and raw_command
                and all(isinstance(part, str) for part in raw_command)
            ):
                normalized_command = tuple(raw_command)
            if normalized_command is not None:
                request_cwd = arguments.get("cwd")
                policy_request = materialize_exec_request(
                    ExecRequest(
                        command=normalized_command,
                        cwd=(request_cwd if isinstance(request_cwd, str) else cwd),
                        env=_policy_environment_pairs(arguments.get("env", ())),
                        stdin=(
                            arguments.get("stdin")
                            if isinstance(arguments.get("stdin"), str)
                            else None
                        ),
                    )
                )
                execution_environment = policy_request.effective_environment
                assert execution_environment is not None
                executable_search_path = executable_search_path_from_env(
                    execution_environment,
                    default=os.defpath,
                )
                command = normalize_command_subject(
                    policy_request.command,
                    cwd=policy_request.cwd,
                    stdin=policy_request.stdin,
                    executable_search_path=executable_search_path,
                    environment_overrides=execution_environment,
                    environment_is_complete=True,
                )
        return self.evaluate(
            build_tool_policy_subject(
                tool_name=tool_name,
                arguments=arguments,
                cwd=cwd,
                command=command,
            )
        )

    def _rules(self) -> tuple[PolicyRule, ...]:
        rules: list[PolicyRule] = []
        rules.extend(
            PolicyRule(
                id=f"{self.rule_id_prefix}.tool.block.{index}",
                matcher=ExactToolNameMatcher(tool_name),
                decision=PolicyDecision.deny(
                    f"Tool {tool_name} is blocked by policy",
                    code="tool_blocked",
                ),
            )
            for index, tool_name in enumerate(self.blocked_tools)
        )
        rules.extend(
            PolicyRule(
                id=f"{self.rule_id_prefix}.tool.ask.{index}",
                matcher=ExactToolNameMatcher(tool_name),
                decision=PolicyDecision.ask(
                    f"Tool {tool_name} requires approval",
                    code="tool_requires_approval",
                ),
            )
            for index, tool_name in enumerate(self.ask_tools)
        )
        rules.extend(
            PolicyRule(
                id=f"{self.rule_id_prefix}.command.block.{index}",
                matcher=CommandSubstringMatcher(substring),
                decision=PolicyDecision.deny(
                    f"Blocked destructive command substring: {substring}",
                    code="command_blocked",
                ),
            )
            for index, substring in enumerate(self.blocked_substrings)
        )
        rules.extend(
            PolicyRule(
                id=f"{self.rule_id_prefix}.command.ask.{index}",
                matcher=CommandSubstringMatcher(substring),
                decision=PolicyDecision.ask(
                    f"Approval recommended for command substring: {substring}",
                    code="command_requires_approval",
                ),
            )
            for index, substring in enumerate(self.ask_substrings)
        )
        rules.extend(
            PolicyRule(
                id=f"{self.rule_id_prefix}.path.block.{index}",
                matcher=PathSubstringMatcher(substring),
                decision=PolicyDecision.deny(
                    f"Path is blocked by policy substring: {substring}",
                    code="path_blocked",
                ),
            )
            for index, substring in enumerate(self.blocked_path_substrings)
        )
        rules.extend(
            PolicyRule(
                id=f"{self.rule_id_prefix}.path.ask.{index}",
                matcher=PathSubstringMatcher(substring),
                decision=PolicyDecision.ask(
                    f"Approval recommended for path substring: {substring}",
                    code="path_requires_approval",
                ),
            )
            for index, substring in enumerate(self.ask_path_substrings)
        )
        rules.append(
            PolicyRule(
                id=f"{self.rule_id_prefix}.command.incomplete",
                matcher=IncompleteCommandMatcher(),
                decision=PolicyDecision.ask(
                    "Command wrapper syntax requires approval",
                    code="command_normalization_incomplete",
                ),
            )
        )
        return tuple(rules)


def _policy_environment_pairs(value: object) -> tuple[tuple[str, str], ...]:
    values = tuple(value.items()) if isinstance(value, Mapping) else value
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        return ()
    pairs: list[tuple[str, str]] = []
    for item in values:
        if isinstance(item, str) or not isinstance(item, (list, tuple)):
            return ()
        pair = tuple(item)
        if len(pair) != 2 or not all(isinstance(part, str) for part in pair):
            return ()
        pairs.append((pair[0], pair[1]))
    return tuple(pairs)
