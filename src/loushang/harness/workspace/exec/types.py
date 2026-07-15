from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

from loushang.harness.workspace.truncation import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES


def _as_tuple_of_strings(
    value: tuple[str, ...] | list[str], field_name: str
) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    return tuple(value)


def _as_tuple_of_output_chunks(
    value: tuple[ExecOutputChunk, ...] | list[ExecOutputChunk],
    field_name: str,
) -> tuple[ExecOutputChunk, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of ExecOutputChunk values")
    normalized = tuple(value)
    if not all(isinstance(chunk, ExecOutputChunk) for chunk in normalized):
        raise TypeError(f"{field_name} must contain ExecOutputChunk values")
    return normalized


def _as_tuple_of_string_pairs(
    value: tuple[tuple[str, str], ...] | list[list[str] | tuple[str, str]],
    field_name: str,
) -> tuple[tuple[str, str], ...]:
    if isinstance(value, str):
        raise TypeError(
            f"{field_name} must be a sequence of string pairs, not a string"
        )
    normalized: list[tuple[str, str]] = []
    for item in value:
        if isinstance(item, str):
            raise TypeError(f"{field_name} must contain 2-item string pairs")
        pair = tuple(item)
        if len(pair) != 2:
            raise TypeError(f"{field_name} must contain 2-item string pairs")
        if not all(isinstance(part, str) for part in pair):
            raise TypeError(f"{field_name} must contain 2-item string pairs")
        normalized.append((pair[0], pair[1]))
    return tuple(normalized)


@dataclass(frozen=True)
class ExecRequest:
    command: tuple[str, ...]
    cwd: str | None = None
    env: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    timeout_seconds: float | None = None
    stdin: str | None = None
    preview_max_lines: int = DEFAULT_MAX_LINES
    preview_max_bytes: int = DEFAULT_MAX_BYTES
    artifact_dir: str | None = None
    capture_full_output: bool = True
    rolling_max_bytes: int = 100 * 1024
    effective_environment: tuple[tuple[str, str], ...] | None = field(
        default=None,
        repr=False,
        compare=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "command", _as_tuple_of_strings(self.command, "command")
        )
        object.__setattr__(self, "env", _as_tuple_of_string_pairs(self.env, "env"))
        if self.effective_environment is not None:
            object.__setattr__(
                self,
                "effective_environment",
                _as_tuple_of_string_pairs(
                    self.effective_environment,
                    "effective_environment",
                ),
            )
        if not isinstance(self.rolling_max_bytes, int):
            raise TypeError("rolling_max_bytes must be an integer")
        if self.rolling_max_bytes < 1:
            raise ValueError("rolling_max_bytes must be >= 1")


def materialize_exec_request(
    request: ExecRequest,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> ExecRequest:
    """Freeze inherited process state before policy evaluation or execution.

    ``env`` remains the caller-visible override set. The complete merged
    environment is stored separately so policy and execution can share one
    request without projecting inherited credentials into approval records.
    """

    requested_cwd = request.cwd if request.cwd is not None else cwd
    effective_cwd = (
        os.path.abspath(requested_cwd)
        if requested_cwd
        else requested_cwd
        if requested_cwd is not None
        else os.getcwd()
    )
    if request.effective_environment is None:
        effective_environment = dict(os.environ if environ is None else environ)
        effective_environment.update(dict(request.env))
        environment_snapshot = tuple(effective_environment.items())
    else:
        environment_snapshot = request.effective_environment
    if request.cwd == effective_cwd and request.effective_environment is not None:
        return request
    return replace(
        request,
        cwd=effective_cwd,
        effective_environment=environment_snapshot,
    )


@dataclass(frozen=True)
class ExecOutputChunk:
    stream: Literal["stdout", "stderr"]
    text: str


ExecUpdateCallback = Callable[[ExecOutputChunk], Awaitable[None] | None]


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    stdout_chunks: tuple[str, ...] = field(default_factory=tuple)
    stderr_chunks: tuple[str, ...] = field(default_factory=tuple)
    output_chunks: tuple[ExecOutputChunk, ...] = field(default_factory=tuple)
    stdout_preview: str = ""
    stderr_preview: str = ""
    stdout_truncated: bool = False
    stdout_truncated_by: str | None = None
    stderr_truncated: bool = False
    stderr_truncated_by: str | None = None
    stdout_artifact_path: str | None = None
    stderr_artifact_path: str | None = None
    stdout_total_lines: int | None = None
    stdout_total_bytes: int | None = None
    stderr_total_lines: int | None = None
    stderr_total_bytes: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stdout_chunks",
            _as_tuple_of_strings(self.stdout_chunks, "stdout_chunks"),
        )
        object.__setattr__(
            self,
            "stderr_chunks",
            _as_tuple_of_strings(self.stderr_chunks, "stderr_chunks"),
        )
        object.__setattr__(
            self,
            "output_chunks",
            _as_tuple_of_output_chunks(self.output_chunks, "output_chunks"),
        )


__all__ = [
    "ExecOutputChunk",
    "ExecRequest",
    "ExecResult",
    "ExecUpdateCallback",
    "materialize_exec_request",
]
