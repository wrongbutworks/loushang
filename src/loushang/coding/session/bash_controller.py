from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loushang.agent import Agent
from loushang.coding.extensions import ExtensionRunner
from loushang.coding.store import SessionManager
from loushang.harness.session import (
    SessionCommandExecutionRuntime,
    UserCommandHookResult,
    UserCommandRequest,
)
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.workspace.protocol import (
    normalize_bash_result_from_protocol,
    project_bash_result_for_protocol,
)
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.workspace.exec import ExecOutputChunk

ExtensionRunnerProvider = Callable[[], ExtensionRunner | None]
ToolRegistryProvider = Callable[[], WorkspaceToolRegistry | None]
ExtensionDiagnosticsSync = Callable[..., None]
OutputCallback = Callable[[ExecOutputChunk], Awaitable[None] | None]
PiStyleOutputCallback = Callable[[str], Awaitable[None] | None]


def _noop_sync_extension_diagnostics(*, phase: str) -> None:
    del phase


@dataclass
class BashController:
    """Coding extension and protocol adapter for Harness command execution."""

    agent: Agent
    session_manager: SessionManager
    get_extension_runner: ExtensionRunnerProvider
    get_tool_registry: ToolRegistryProvider
    sync_extension_diagnostics: ExtensionDiagnosticsSync = (
        _noop_sync_extension_diagnostics
    )
    _runtime: SessionCommandExecutionRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._runtime = SessionCommandExecutionRuntime(
            command_name="Bash",
            get_cwd=self.session_manager.get_cwd,
            get_definition=self._get_bash_definition,
            build_execution_params=_build_bash_execution_params,
            create_call_id=self._create_call_id,
            append_record=self.session_manager.append_message,
            refresh_context=self._refresh_context,
            before_execute=self._before_bash,
        )

    @property
    def is_running(self) -> bool:
        return self._runtime.is_running

    @property
    def has_pending_messages(self) -> bool:
        return False

    async def execute_bash(
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
        on_output: OutputCallback | None = None,
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
        on_output: OutputCallback | None = None,
        operations: object | None = None,
    ) -> dict[str, object]:
        """Expose the selected command-tool execution port to Harness."""

        return await self.execute_bash(
            command,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
            exclude_from_context=exclude_from_context,
            on_output=on_output,
            operations=operations,
        )

    async def execute_pi_style(
        self,
        command: str,
        on_chunk: PiStyleOutputCallback | None = None,
        options: dict[str, object] | None = None,
    ) -> dict[str, object]:
        async def _on_output(chunk: ExecOutputChunk) -> None:
            if on_chunk is None:
                return
            result = on_chunk(chunk.text)
            if inspect.isawaitable(result):
                await result

        options = dict(options or {})
        cwd = options.get("cwd")
        stdin = options.get("stdin")
        result = await self.execute_bash(
            command,
            cwd=cwd if isinstance(cwd, str) else None,
            timeout_seconds=_option_float(
                options.get("timeout_seconds", options.get("timeoutSeconds"))
            ),
            stdin=stdin if isinstance(stdin, str) else None,
            exclude_from_context=bool(
                options.get(
                    "excludeFromContext", options.get("exclude_from_context", False)
                )
            ),
            on_output=_on_output if on_chunk is not None else None,
            operations=options.get("operations"),
        )
        return project_bash_result_for_protocol(result)

    def abort(self) -> None:
        self._runtime.abort()

    async def record_result(
        self,
        *,
        command: str,
        result: dict[str, object],
        exclude_from_context: bool,
    ) -> None:
        await self._runtime.record_result(
            command=command,
            result=result,
            exclude_from_context=exclude_from_context,
        )

    async def record_pi_style_result(
        self,
        command: str,
        result: dict[str, object],
        options: dict[str, object] | None = None,
    ) -> None:
        options = dict(options or {})
        await self.record_result(
            command=command,
            result=normalize_bash_result_from_protocol(result),
            exclude_from_context=bool(
                options.get(
                    "excludeFromContext", options.get("exclude_from_context", False)
                )
            ),
        )

    def _get_bash_definition(self) -> ToolDefinition | None:
        tool_registry = self.get_tool_registry()
        if tool_registry is None:
            raise RuntimeError("Bash execution requires a tool registry")
        try:
            return tool_registry.get_definition("bash")
        except KeyError as exc:
            raise RuntimeError("Bash tool is not registered") from exc

    def _create_call_id(self) -> str:
        return (
            f"bash-{self.session_manager.get_session_record().session_id}-"
            f"{len(self.session_manager.get_entries())}"
        )

    def _refresh_context(self) -> None:
        self.agent.state.set_messages(
            list(self.session_manager.build_session_context().messages)
        )

    async def _before_bash(
        self,
        request: UserCommandRequest,
    ) -> UserCommandHookResult | None:
        extension_runner = self.get_extension_runner()
        if extension_runner is None or not extension_runner.has_handlers("user_bash"):
            return None
        event_result = await extension_runner.emit_user_bash(
            {
                "type": "user_bash",
                "command": request.command,
                "exclude_from_context": request.exclude_from_context,
                "cwd": request.cwd,
            },
            cwd=request.cwd,
        )
        self.sync_extension_diagnostics(phase="runtime")
        result = _bash_result_from_extension_user_bash_result(event_result)
        if result is not None:
            return UserCommandHookResult(result=result)
        return UserCommandHookResult(
            operations=_bash_operations_from_extension_user_bash_result(event_result)
        )


def _bash_result_from_extension_user_bash_result(
    event_result: object | None,
) -> dict[str, object] | None:
    if event_result is None:
        return None
    result = (
        event_result.get("result")
        if isinstance(event_result, dict)
        else getattr(event_result, "result", None)
    )
    if not isinstance(result, dict):
        return None
    return normalize_bash_result_from_protocol(result)


def _build_bash_execution_params(command: str, cwd: str) -> dict[str, object]:
    return {"command": ["/bin/bash", "-lc", command], "cwd": cwd}


def _bash_operations_from_extension_user_bash_result(
    event_result: object | None,
) -> object | None:
    if event_result is None:
        return None
    if isinstance(event_result, dict):
        return event_result.get("operations")
    return getattr(event_result, "operations", None)


def _option_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None
