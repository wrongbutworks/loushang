from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

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
from loushang.harness.capabilities.prompt_preflight import PromptPreflightResult
from loushang.harness.commands import (
    CommandDispatchOutcome,
    ParsedSlashCommand,
    SessionCommandDescriptor,
    split_slash_command,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.extensions.types import ResolvedCommand
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.session import (
    CommandRuntimeSource,
    ExtensionCommandSourceRuntime,
    ResourceCommandSourceRuntime,
    SessionCommandRuntime,
    SessionDiagnosticScope,
    SessionDiagnosticsRuntime,
)


@dataclass
class CommandController:
    session_manager: SessionManager
    get_extension_runner: Callable[[], ExtensionRunner | None]
    get_resource_bundle: Callable[[], ResourceBundle | None]
    get_diagnostics_service: Callable[[], DiagnosticsService | None]
    builtin_backend: BuiltinCommandBackend | None = None
    diagnostics_runtime: SessionDiagnosticsRuntime | None = None
    pack_composer: CapabilityPackComposer = field(
        default_factory=CapabilityPackComposer
    )
    _runtime: SessionCommandRuntime[
        SessionCommandDescriptor, CommandExecutionResult
    ] = field(init=False, repr=False)
    _extension_source: ExtensionCommandSourceRuntime[CommandExecutionResult] = field(
        init=False,
        repr=False,
    )
    _resource_source: ResourceCommandSourceRuntime[CommandExecutionResult] = field(
        init=False,
        repr=False,
    )
    _diagnostics_runtime: SessionDiagnosticsRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._diagnostics_runtime = (
            self.diagnostics_runtime
            or SessionDiagnosticsRuntime(
                diagnostics_service=self.get_diagnostics_service(),
                get_scope=lambda: SessionDiagnosticScope(
                    session_id=self.session_manager.get_header().conversation_id,
                    entry_id=self.session_manager.get_leaf_id(),
                ),
                get_extension_diagnostics=lambda: None,
            )
        )
        self._extension_source = ExtensionCommandSourceRuntime(
            get_provider=self.get_extension_runner,
            get_cwd=self.session_manager.get_cwd,
            result_factory=lambda command: CommandExecutionResult(
                invocation_name=command.invocation_name,
                result=None,
            ),
            record_error=lambda command, exc: (
                self._diagnostics_runtime.record_extension_command_error(
                    command=command,
                    exc=exc,
                )
            ),
        )
        self._resource_source = ResourceCommandSourceRuntime(
            get_resource_bundle=self.get_resource_bundle,
            record_diagnostics=self._diagnostics_runtime.record_preflight_diagnostics,
            record_command_not_found=self._diagnostics_runtime.record_command_not_found,
            result_factory=lambda invocation_name, source, text: CommandExecutionResult(
                invocation_name=invocation_name,
                result={"source": source, "text": text},
            ),
        )
        self._runtime = SessionCommandRuntime(
            sources=(
                CommandRuntimeSource(
                    pack_id="coding.builtin-commands",
                    source="product",
                    descriptor_priority=300,
                    handler_priority=200,
                    list_descriptors=self._list_builtin_commands,
                    handler_name="builtin",
                    handler=self._dispatch_builtin_command,
                ),
                CommandRuntimeSource(
                    pack_id="coding.extension-commands",
                    source="extension",
                    descriptor_priority=200,
                    handler_priority=300,
                    list_descriptors=self._extension_source.list_descriptors,
                    handler_name="extension",
                    handler=self._extension_source.dispatch,
                ),
                CommandRuntimeSource(
                    pack_id="coding.resource-commands",
                    source="product",
                    descriptor_priority=100,
                    handler_priority=100,
                    list_descriptors=self._resource_source.list_descriptors,
                    handler_name="resource",
                    handler=self._resource_source.dispatch,
                ),
            ),
            pack_composer=self.pack_composer,
        )

    def list_commands(self) -> list[SessionCommandDescriptor]:
        return self._runtime.list_commands()

    async def execute_command_async(
        self, invocation_name: str, args: str
    ) -> CommandExecutionResult | None:
        return await self._runtime.execute(invocation_name, args)

    def _list_builtin_commands(self) -> list[SessionCommandDescriptor]:
        builtin_commands: list[SessionCommandDescriptor] = []
        if self.builtin_backend is not None:
            builtin_commands.extend(list_builtin_command_descriptors())
        return builtin_commands

    async def _dispatch_builtin_command(
        self,
        invocation: ParsedSlashCommand,
    ) -> CommandDispatchOutcome[CommandExecutionResult]:
        result = await self.execute_builtin_command_async(
            invocation.name, invocation.args
        )
        if result is None:
            return CommandDispatchOutcome.unhandled()
        return CommandDispatchOutcome.handled_result(result)

    async def execute_builtin_command_async(
        self, invocation_name: str, args: str
    ) -> CommandExecutionResult | None:
        if self.builtin_backend is None:
            return None
        return await execute_builtin_command_async(
            invocation_name, args, self.builtin_backend
        )

    def execute_resource_command(
        self, invocation_name: str, args: str
    ) -> CommandExecutionResult | None:
        return self._resource_source.execute(invocation_name, args)

    def record_command_not_found(self, invocation_name: str, args: str) -> None:
        self._diagnostics_runtime.record_command_not_found(invocation_name, args)

    async def get_command_argument_completions(
        self, invocation_name: str, prefix: str
    ) -> list[object] | None:
        return await self._extension_source.get_argument_completions(
            invocation_name,
            prefix,
        )

    def extract_extension_command_invocation(
        self, user_input: str
    ) -> tuple[str, str] | None:
        return self._extension_source.extract_invocation(user_input)

    def extract_builtin_command_invocation(
        self, user_input: str
    ) -> tuple[str, str] | None:
        if self.builtin_backend is None:
            return None
        parsed = split_slash_command(user_input)
        if parsed is None:
            return None
        invocation_name, args = parsed
        if not is_builtin_command(invocation_name):
            return None
        return invocation_name, args

    def raise_if_queued_extension_command(self, user_input: str) -> None:
        command = self.extract_extension_command_invocation(user_input)
        if command is not None:
            invocation_name, _args = command
            raise RuntimeError(
                f'Extension command "/{invocation_name}" cannot be queued. '
                "Use prompt() or execute the command when not streaming."
            )

    def preflight_user_input(
        self, user_input: str, *, allow_extension_commands: bool = True
    ):
        del allow_extension_commands
        return self._resource_source.preflight_user_input(user_input)

    async def preflight_user_input_async(
        self, user_input: str, *, allow_extension_commands: bool = True
    ):
        if allow_extension_commands:
            command = self.extract_extension_command_invocation(user_input)
            if command is not None:
                invocation_name, args = command
                await self.execute_command_async(invocation_name, args)
                return PromptPreflightResult(text=user_input, consumed=True)
            command = self.extract_builtin_command_invocation(user_input)
            if command is not None:
                invocation_name, args = command
                await self.execute_command_async(invocation_name, args)
                return PromptPreflightResult(text=user_input, consumed=True)
        return self._resource_source.preflight_user_input(user_input)

    def record_preflight_diagnostics(
        self, diagnostics: tuple[ResourceDiagnostic, ...]
    ) -> None:
        self._diagnostics_runtime.record_preflight_diagnostics(diagnostics)

    def record_extension_command_error(
        self, *, command: ResolvedCommand, exc: BaseException
    ) -> None:
        self._diagnostics_runtime.record_extension_command_error(
            command=command,
            exc=exc,
        )
