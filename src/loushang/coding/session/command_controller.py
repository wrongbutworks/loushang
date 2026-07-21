"""Coding command bindings over the shared session command controller."""

from __future__ import annotations

from collections.abc import Callable

from loushang.coding.extensions import ExtensionRunner
from loushang.coding.session.types import CommandExecutionResult
from loushang.coding.session_manager import SessionManager
from loushang.harness.capabilities.packs import CapabilityPackComposer
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session import (
    SessionCommandController,
    SessionDiagnosticsRuntime,
    StandardSessionCommandPorts,
    execute_standard_session_command_async,
    is_standard_session_command,
    list_standard_session_command_descriptors,
    project_standard_session_command_result,
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
        standard_ports: StandardSessionCommandPorts | None = None,
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
                list_standard_session_command_descriptors
                if standard_ports is not None
                else (lambda: [])
            ),
            builtin_executor=(
                (lambda invocation_name, args: _execute_standard_command(
                    invocation_name, args, standard_ports
                ))
                if standard_ports is not None
                else None
            ),
            builtin_matcher=is_standard_session_command,
            diagnostics_runtime=diagnostics_runtime,
            pack_composer=pack_composer or CapabilityPackComposer(),
        )


async def _execute_standard_command(
    invocation_name: str,
    args: str,
    ports: StandardSessionCommandPorts | None,
) -> CommandExecutionResult | None:
    if ports is None:
        return None
    result = await execute_standard_session_command_async(
        invocation_name,
        args,
        ports,
    )
    if result is None:
        return None
    return CommandExecutionResult(
        invocation_name=invocation_name,
        result=project_standard_session_command_result(result),
    )
__all__ = ["CommandController"]
