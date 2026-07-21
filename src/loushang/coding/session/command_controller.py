"""Coding command bindings over the shared session command controller."""

from __future__ import annotations

from collections.abc import Callable

from loushang.coding.extensions import ExtensionRunner
from loushang.coding.session.builtin_commands import (
    BuiltinCommandBackend,
    execute_builtin_command_async,
    is_builtin_command,
    list_builtin_command_descriptors,
)
from loushang.coding.session.types import CommandExecutionResult
from loushang.coding.store import SessionManager
from loushang.harness.capabilities.packs import CapabilityPackComposer
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session import (
    SessionCommandController,
    SessionDiagnosticsRuntime,
)


class CommandController(SessionCommandController[CommandExecutionResult]):
    """Bind Coding builtin command semantics to the shared source runtime."""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        get_extension_runner: Callable[[], ExtensionRunner | None],
        get_resource_bundle: Callable[[], ResourceBundle | None],
        get_diagnostics_service: Callable[[], DiagnosticsService | None],
        builtin_backend: BuiltinCommandBackend | None = None,
        diagnostics_runtime: SessionDiagnosticsRuntime | None = None,
        pack_composer: CapabilityPackComposer | None = None,
    ) -> None:
        super().__init__(
            session_manager=session_manager,
            get_extension_runner=get_extension_runner,
            get_resource_bundle=get_resource_bundle,
            get_diagnostics_service=get_diagnostics_service,
            result_factory=lambda invocation_name, result: CommandExecutionResult(
                invocation_name=invocation_name,
                result=result,
            ),
            extension_result_factory=lambda command: CommandExecutionResult(
                invocation_name=command.invocation_name,
                result=None,
            ),
            builtin_descriptors=(
                list_builtin_command_descriptors
                if builtin_backend is not None
                else (lambda: [])
            ),
            builtin_executor=(
                (lambda invocation_name, args: execute_builtin_command_async(
                    invocation_name,
                    args,
                    builtin_backend,
                ))
                if builtin_backend is not None
                else None
            ),
            builtin_matcher=is_builtin_command,
            diagnostics_runtime=diagnostics_runtime,
            pack_composer=pack_composer or CapabilityPackComposer(),
        )
__all__ = ["CommandController"]
