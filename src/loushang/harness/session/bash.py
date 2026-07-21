"""Standard shell-command execution binding for composed Agent sessions.

Products provide the tool definition, transcript append callback, and optional
extension hook.  The execution, abort, stream forwarding, and command-record
normalization remain shared.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from loushang.harness.session.capabilities import (
    CommandDefinitionProvider,
    CommandHook,
    CommandOutputCallback,
    CommandParametersBuilder,
    SessionCommandExecutionRuntime,
)

CallIdFactory = Callable[[], str]
AppendCommandRecord = Callable[[object], Awaitable[object]]
ContextRefresher = Callable[[], None]


@dataclass(frozen=True)
class BashExecutionPorts:
    """Product callbacks needed to bind the standard Bash runtime."""

    get_cwd: Callable[[], str]
    get_definition: CommandDefinitionProvider
    create_call_id: CallIdFactory
    append_record: AppendCommandRecord
    refresh_context: ContextRefresher
    before_execute: CommandHook | None = None
    build_execution_params: CommandParametersBuilder | None = None


class BashExecutionRuntime:
    """Reusable shell execution surface over ``SessionCommandExecutionRuntime``."""

    def __init__(self, ports: BashExecutionPorts, *, shell_path: str = "/bin/bash"):
        self._runtime = SessionCommandExecutionRuntime(
            command_name="Bash",
            get_cwd=ports.get_cwd,
            get_definition=ports.get_definition,
            build_execution_params=ports.build_execution_params
            or _default_execution_params(shell_path),
            create_call_id=ports.create_call_id,
            append_record=ports.append_record,
            refresh_context=ports.refresh_context,
            before_execute=ports.before_execute,
        )

    @property
    def is_running(self) -> bool:
        return self._runtime.is_running

    @property
    def has_pending_messages(self) -> bool:
        return False

    async def execute(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: list[list[str] | tuple[str, str]]
        | tuple[tuple[str, str], ...]
        | None = None,
        timeout_seconds: float | None = None,
        stdin: str | None = None,
        exclude_from_context: bool = False,
        on_output: CommandOutputCallback | None = None,
        operations: object | None = None,
    ) -> dict[str, object]:
        return await self._runtime.execute(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            exclude_from_context=exclude_from_context,
            on_output=on_output,
            operations=operations,
        )

    async def record_result(
        self,
        *,
        command: str,
        result: Mapping[str, object],
        exclude_from_context: bool,
    ) -> None:
        await self._runtime.record_result(
            command=command,
            result=result,
            exclude_from_context=exclude_from_context,
        )

    def abort(self) -> None:
        self._runtime.abort()


def _default_execution_params(shell_path: str) -> CommandParametersBuilder:
    def build(command: str, cwd: str) -> Mapping[str, object]:
        return {"command": [shell_path, "-lc", command], "cwd": cwd}

    return build


__all__ = ["BashExecutionPorts", "BashExecutionRuntime"]
