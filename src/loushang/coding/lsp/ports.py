"""Consumer-owned ports used by the first Coding LSP vertical slice.

The process contracts are deliberately structural.  The production Harness
launcher will satisfy this shape; tests use an in-memory Fake Launcher.  This
module owns no operating-system spawn path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessLaunchRequest:
    command: tuple[str, ...]
    cwd: str
    effective_environment: tuple[tuple[str, str], ...] = field(
        default_factory=tuple,
        repr=False,
    )

    def __post_init__(self) -> None:
        command = tuple(self.command)
        if not command or any(
            not isinstance(part, str) or not part for part in command
        ):
            raise ValueError("process command must be a non-empty argv tuple")
        requested_cwd = Path(self.cwd).expanduser()
        if not requested_cwd.is_absolute():
            raise ValueError("process cwd must be an absolute path")
        cwd = requested_cwd.resolve()
        environment = tuple(self.effective_environment)
        if any(
            not isinstance(name, str) or not name or not isinstance(value, str)
            for name, value in environment
        ):
            raise TypeError("effective environment must contain string pairs")
        names = tuple(name for name, _ in environment)
        if len(set(names)) != len(names):
            raise ValueError("effective environment names must be unique")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "cwd", str(cwd))
        object.__setattr__(
            self,
            "effective_environment",
            environment,
        )


@dataclass(frozen=True, slots=True)
class ProcessExit:
    return_code: int | None


@dataclass(frozen=True, slots=True)
class ProcessStderrTail:
    content: bytes = b""
    truncated: bool = False


class ProcessHandle(Protocol):
    """The byte-stream and lifetime subset consumed by the LSP client."""

    async def read_stdout(self, max_bytes: int = 65536) -> bytes: ...

    async def write_stdin(self, data: bytes) -> None: ...

    async def close_stdin(self) -> None: ...

    async def wait(self) -> ProcessExit: ...

    async def terminate(self) -> ProcessExit: ...

    async def close(self) -> None: ...

    def stderr_tail(self) -> ProcessStderrTail: ...


class AuthorizedProcessLauncher(Protocol):
    """Execution-scope-bound process launch port supplied by Harness."""

    async def start(
        self,
        request: ProcessLaunchRequest,
        *,
        correlation_id: str,
        signal: object | None = None,
    ) -> ProcessHandle: ...


TextReadResult = str | Awaitable[str]
WorkspaceTextReader = Callable[[Path], TextReadResult]
PathExists = Callable[[Path], bool]


__all__ = [
    "AuthorizedProcessLauncher",
    "PathExists",
    "ProcessExit",
    "ProcessHandle",
    "ProcessLaunchRequest",
    "ProcessStderrTail",
    "TextReadResult",
    "WorkspaceTextReader",
]
