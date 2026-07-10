from __future__ import annotations

import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from os.path import basename
from pathlib import Path
from typing import Any

from loushang.coding.policy.types import PolicyDecision
from loushang.harness.workspace.exec import ExecRequest

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
_SHELL_ENTRY_BASENAMES: tuple[str, ...] = (
    "sh",
    "bash",
    "dash",
    "zsh",
    "ksh",
)
_LEADING_WRAPPER_BASENAMES: tuple[str, ...] = (
    "env",
    "sudo",
)
_ENV_NO_VALUE_OPTIONS: tuple[str, ...] = (
    "-i",
    "--ignore-environment",
    "-0",
    "--null",
    "-v",
    "--debug",
)
_ENV_VALUE_OPTIONS: tuple[str, ...] = (
    "-u",
    "--unset",
    "-C",
    "--chdir",
    "-S",
    "--split-string",
    "-a",
    "--argv0",
    "-f",
    "--file",
    "--block-signal",
    "--default-signal",
    "--ignore-signal",
)
_SUDO_VALUE_OPTIONS: tuple[str, ...] = (
    "-a",
    "--auth-type",
    "-c",
    "--login-class",
    "-u",
    "--user",
    "-g",
    "--group",
    "-h",
    "--host",
    "-p",
    "--prompt",
    "-r",
    "--role",
    "-t",
    "--type",
    "-C",
    "--close-from",
    "-D",
    "--chdir",
    "-R",
    "--chroot",
    "-T",
    "--command-timeout",
)


def _normalize_substrings(
    values: tuple[str, ...] | list[str], field_name: str, defaults: tuple[str, ...]
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


def _normalize_strings(values: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    return _normalize_substrings(values, field_name, ())


def _shell_payload(command: tuple[str, ...]) -> str | None:
    if len(command) < 3:
        return None

    executable = basename(command[0])
    if executable not in _SHELL_ENTRY_BASENAMES:
        return None

    shell_flag = command[1]
    if "c" not in shell_flag:
        return None

    return command[2]


def _is_env_assignment(token: str) -> bool:
    if "=" not in token:
        return False

    name, _, _ = token.partition("=")
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(ch.isalnum() or ch == "_" for ch in name[1:])


def _split_env_string(value: str, remainder: tuple[str, ...]) -> tuple[str, ...]:
    try:
        split_tokens = tuple(shlex.split(value))
    except ValueError:
        return ("sh", "-lc", value, *remainder)
    return (*split_tokens, *remainder)


def _unwrap_env_command(command: tuple[str, ...]) -> tuple[str, ...]:
    while command:
        head = command[0]
        if head == "--":
            return command[1:]
        if head in _ENV_NO_VALUE_OPTIONS:
            command = command[1:]
            continue
        if head in ("-S", "--split-string"):
            if len(command) < 2:
                return ()
            return _split_env_string(command[1], command[2:])
        if head.startswith("--split-string="):
            return _split_env_string(head.partition("=")[2], command[1:])
        if head in _ENV_VALUE_OPTIONS:
            if len(command) < 2:
                return ()
            command = command[2:]
            continue
        if any(head.startswith(f"{option}=") for option in _ENV_VALUE_OPTIONS if option.startswith("--")):
            command = command[1:]
            continue
        if head.startswith("-"):
            command = command[1:]
            continue
        if _is_env_assignment(head):
            command = command[1:]
            continue
        break
    return command


def _unwrap_leading_wrappers(command: tuple[str, ...]) -> tuple[str, ...]:
    while command and basename(command[0]) in _LEADING_WRAPPER_BASENAMES:
        wrapper = basename(command[0])
        command = command[1:]

        if wrapper == "env":
            command = _unwrap_env_command(command)
        elif wrapper == "sudo":
            while command:
                head = command[0]
                if not head.startswith("-"):
                    break
                if head in _SUDO_VALUE_OPTIONS:
                    if len(command) < 2:
                        return ()
                    command = command[2:]
                    continue
                if any(head.startswith(f"{option}=") for option in _SUDO_VALUE_OPTIONS if option.startswith("--")):
                    command = command[1:]
                    continue
                command = command[1:]
    return command


def _direct_command_tokens(command: tuple[str, ...]) -> tuple[str, ...]:
    command = _unwrap_leading_wrappers(command)
    if not command:
        return ()
    return (basename(command[0]), *command[1:])


def _matches_substring(command: tuple[str, ...], substring: str) -> bool:
    command = _unwrap_leading_wrappers(command)
    payload = _shell_payload(command)
    if payload is not None:
        return substring in payload

    tokens = _direct_command_tokens(command)
    rule_tokens = tuple(part for part in substring.split() if part)
    if not rule_tokens:
        return False

    if len(rule_tokens) == 1:
        return rule_tokens[0] in tokens

    window_size = len(rule_tokens)
    for index in range(len(tokens) - window_size + 1):
        if tokens[index : index + window_size] == rule_tokens:
            return True
    return False


@dataclass(frozen=True)
class PolicyEngine:
    blocked_substrings: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_BLOCKED_SUBSTRINGS)
    ask_substrings: tuple[str, ...] = field(default_factory=lambda: _DEFAULT_ASK_SUBSTRINGS)
    blocked_tools: tuple[str, ...] = field(default_factory=tuple)
    ask_tools: tuple[str, ...] = field(default_factory=tuple)
    blocked_path_substrings: tuple[str, ...] = field(default_factory=tuple)
    ask_path_substrings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "blocked_substrings",
            _normalize_substrings(self.blocked_substrings, "blocked_substrings", _DEFAULT_BLOCKED_SUBSTRINGS),
        )
        object.__setattr__(
            self,
            "ask_substrings",
            _normalize_substrings(self.ask_substrings, "ask_substrings", _DEFAULT_ASK_SUBSTRINGS),
        )
        object.__setattr__(self, "blocked_tools", _normalize_strings(self.blocked_tools, "blocked_tools"))
        object.__setattr__(self, "ask_tools", _normalize_strings(self.ask_tools, "ask_tools"))
        object.__setattr__(
            self,
            "blocked_path_substrings",
            _normalize_strings(self.blocked_path_substrings, "blocked_path_substrings"),
        )
        object.__setattr__(
            self,
            "ask_path_substrings",
            _normalize_strings(self.ask_path_substrings, "ask_path_substrings"),
        )

    def evaluate_action(self, *, tool_name: str, exec_request: ExecRequest) -> PolicyDecision:
        for substring in self.blocked_substrings:
            if _matches_substring(exec_request.command, substring):
                return PolicyDecision.deny(
                    f"Blocked destructive command substring: {substring}",
                    code="command_blocked",
                )

        for substring in self.ask_substrings:
            if _matches_substring(exec_request.command, substring):
                return PolicyDecision.ask(
                    f"Approval recommended for command substring: {substring}",
                    code="command_requires_approval",
                )

        return PolicyDecision.allow()

    def evaluate_tool_call(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
        cwd: str | None = None,
    ) -> PolicyDecision:
        if tool_name in self.blocked_tools:
            return PolicyDecision.deny(f"Tool {tool_name} is blocked by policy", code="tool_blocked")
        if tool_name in self.ask_tools:
            return PolicyDecision.ask(f"Tool {tool_name} requires approval", code="tool_requires_approval")

        if tool_name == "bash":
            command = arguments.get("command")
            if isinstance(command, str):
                request_cwd = arguments.get("cwd")
                exec_request = ExecRequest(
                    command=("/bin/sh", "-lc", command),
                    cwd=request_cwd if isinstance(request_cwd, str) else (cwd or ""),
                )
                return self.evaluate_action(tool_name=tool_name, exec_request=exec_request)

        path_candidates = _path_candidates(arguments, cwd=cwd)
        for substring in self.blocked_path_substrings:
            if any(substring in candidate for candidate in path_candidates):
                return PolicyDecision.deny(
                    f"Path is blocked by policy substring: {substring}",
                    code="path_blocked",
                )
        for substring in self.ask_path_substrings:
            if any(substring in candidate for candidate in path_candidates):
                return PolicyDecision.ask(
                    f"Approval recommended for path substring: {substring}",
                    code="path_requires_approval",
                )

        return PolicyDecision.allow()


def _path_candidates(arguments: Mapping[str, Any], *, cwd: str | None) -> tuple[str, ...]:
    raw_path = arguments.get("path", arguments.get("file_path"))
    if not isinstance(raw_path, str) or not raw_path:
        return ()
    candidates = [raw_path]
    try:
        path = Path(raw_path).expanduser()
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
        candidates.append(str(path.resolve()))
    except (OSError, RuntimeError, ValueError):
        pass
    return tuple(dict.fromkeys(candidates))
