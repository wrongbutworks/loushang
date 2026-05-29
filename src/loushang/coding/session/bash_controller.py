from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import time

from loushang.agent import AbortController, Agent
from loushang.coding.exec import ExecOutputChunk
from loushang.coding.extensions import ExtensionRunner
from loushang.coding.message import BashExecutionMessage
from loushang.coding.store import SessionManager
from loushang.coding.tools import ToolRegistry
from loushang.coding.tools.protocol import normalize_bash_result_from_protocol, project_bash_result_for_protocol


ExtensionRunnerProvider = Callable[[], ExtensionRunner | None]
ToolRegistryProvider = Callable[[], ToolRegistry | None]
ExtensionDiagnosticsSync = Callable[..., None]
OutputCallback = Callable[[ExecOutputChunk], Awaitable[None] | None]
PiStyleOutputCallback = Callable[[str], Awaitable[None] | None]


def _noop_sync_extension_diagnostics(*, phase: str) -> None:
    del phase


@dataclass
class BashController:
    agent: Agent
    session_manager: SessionManager
    get_extension_runner: ExtensionRunnerProvider
    get_tool_registry: ToolRegistryProvider
    sync_extension_diagnostics: ExtensionDiagnosticsSync = _noop_sync_extension_diagnostics

    _bash_abort_controller: AbortController | None = None

    @property
    def is_running(self) -> bool:
        return self._bash_abort_controller is not None

    @property
    def has_pending_messages(self) -> bool:
        return False

    async def execute_bash(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: list[list[str] | tuple[str, str]] | tuple[tuple[str, str], ...] | None = None,
        timeout_seconds: float | None = None,
        stdin: str | None = None,
        exclude_from_context: bool = False,
        on_output: OutputCallback | None = None,
        operations: object | None = None,
    ) -> dict[str, object]:
        if self._bash_abort_controller is not None:
            raise RuntimeError("Bash execution already in progress")
        effective_cwd = cwd or self.session_manager.get_cwd()
        selected_operations = operations
        extension_runner = self.get_extension_runner()
        if extension_runner is not None and extension_runner.has_handlers("user_bash"):
            event_result = await extension_runner.emit_user_bash(
                {
                    "type": "user_bash",
                    "command": command,
                    "exclude_from_context": exclude_from_context,
                    "cwd": effective_cwd,
                },
                cwd=effective_cwd,
            )
            bash_result = _bash_result_from_extension_user_bash_result(event_result)
            if bash_result is not None:
                self.record_result(
                    command=command,
                    result=bash_result,
                    exclude_from_context=exclude_from_context,
                )
                self.sync_extension_diagnostics(phase="runtime")
                return bash_result
            extension_operations = _bash_operations_from_extension_user_bash_result(event_result)
            if extension_operations is not None:
                selected_operations = extension_operations
            self.sync_extension_diagnostics(phase="runtime")

        tool_registry = self.get_tool_registry()
        if tool_registry is None:
            raise RuntimeError("Bash execution requires a tool registry")

        try:
            bash_definition = tool_registry.get_definition("bash")
        except KeyError as exc:
            raise RuntimeError("Bash tool is not registered") from exc

        controller = AbortController()
        self._bash_abort_controller = controller
        streamed_chunks: list[str] = []

        async def _forward_update(partial_result) -> None:
            details = getattr(partial_result, "details", None)
            stream = details.get("stream") if isinstance(details, dict) else None
            if stream not in {"stdout", "stderr"}:
                return
            text = "".join(block.text for block in partial_result.content if getattr(block, "type", None) == "text")
            if not text:
                return
            streamed_chunks.append(text)
            if on_output is None:
                return
            forwarded = on_output(ExecOutputChunk(stream=stream, text=text))
            if inspect.isawaitable(forwarded):
                await forwarded

        params: dict[str, object] = {
            "command": ["/bin/bash", "-lc", command],
            "cwd": effective_cwd,
        }
        if env is not None:
            params["env"] = [list(pair) for pair in env]
        if timeout_seconds is not None:
            params["timeout_seconds"] = timeout_seconds
        if stdin is not None:
            params["stdin"] = stdin
        if selected_operations is not None:
            params["__operations"] = selected_operations

        try:
            tool_result = await bash_definition.execute(
                f"bash-{self.session_manager.get_session_record().session_id}-{len(self.session_manager.get_entries())}",
                params,
                controller.signal,
                _forward_update,
            )
            bash_result = _bash_result_from_tool_result(tool_result)
        except RuntimeError as exc:
            if "Command aborted" not in str(exc) or not getattr(controller.signal, "aborted", False):
                raise
            bash_result = {
                "output": "".join(streamed_chunks),
                "exit_code": None,
                "cancelled": True,
                "truncated": False,
                "full_output_path": None,
            }
        finally:
            self._bash_abort_controller = None

        self.record_result(
            command=command,
            result=bash_result,
            exclude_from_context=exclude_from_context,
        )
        return bash_result

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
        result = await self.execute_bash(
            command,
            cwd=options.get("cwd") if isinstance(options.get("cwd"), str) else None,
            timeout_seconds=(
                float(options["timeout_seconds"])
                if isinstance(options.get("timeout_seconds"), int | float)
                else (
                    float(options["timeoutSeconds"])
                    if isinstance(options.get("timeoutSeconds"), int | float)
                    else None
                )
            ),
            stdin=options.get("stdin") if isinstance(options.get("stdin"), str) else None,
            exclude_from_context=bool(options.get("excludeFromContext", options.get("exclude_from_context", False))),
            on_output=_on_output if on_chunk is not None else None,
            operations=options.get("operations"),
        )
        return project_bash_result_for_protocol(result)

    def abort(self) -> None:
        if self._bash_abort_controller is not None:
            self._bash_abort_controller.abort()

    def record_result(
        self,
        *,
        command: str,
        result: dict[str, object],
        exclude_from_context: bool,
    ) -> None:
        self.session_manager.append_message(
            BashExecutionMessage(
                role="bashExecution",
                command=command,
                output=str(result.get("output") or ""),
                exit_code=result.get("exit_code") if isinstance(result.get("exit_code"), int) else None,
                cancelled=bool(result.get("cancelled", False)),
                truncated=bool(result.get("truncated", False)),
                full_output_path=(
                    str(result["full_output_path"])
                    if isinstance(result.get("full_output_path"), str) and result.get("full_output_path")
                    else None
                ),
                timestamp=time(),
                exclude_from_context=exclude_from_context,
            )
        )
        session_context = self.session_manager.build_session_context()
        self.agent.state.set_messages(session_context.messages)

    def record_pi_style_result(
        self,
        command: str,
        result: dict[str, object],
        options: dict[str, object] | None = None,
    ) -> None:
        options = dict(options or {})
        normalized = normalize_bash_result_from_protocol(result)
        self.record_result(
            command=command,
            result=normalized,
            exclude_from_context=bool(options.get("excludeFromContext", options.get("exclude_from_context", False))),
        )


def _bash_result_from_tool_result(tool_result) -> dict[str, object]:
    details = tool_result.details if isinstance(tool_result.details, dict) else {}
    output = "".join(block.text for block in tool_result.content if getattr(block, "type", None) == "text")
    stderr = details.get("stderr")
    if isinstance(stderr, str) and stderr and not output.endswith(stderr):
        output = output + stderr
    return {
        "output": output,
        "exit_code": details.get("exit_code"),
        "cancelled": bool(details.get("cancelled", False)),
        "truncated": bool(details.get("truncated", False) or details.get("stderr_truncated", False)),
        "full_output_path": details.get("stdout_artifact_path") or details.get("stderr_artifact_path"),
    }


def _bash_result_from_extension_user_bash_result(event_result: object | None) -> dict[str, object] | None:
    if event_result is None:
        return None
    result = event_result.get("result") if isinstance(event_result, dict) else getattr(event_result, "result", None)
    if not isinstance(result, dict):
        return None
    return normalize_bash_result_from_protocol(result)


def _bash_operations_from_extension_user_bash_result(event_result: object | None) -> object | None:
    if event_result is None:
        return None
    if isinstance(event_result, dict):
        return event_result.get("operations")
    return getattr(event_result, "operations", None)
