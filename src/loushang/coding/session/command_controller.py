from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from loushang.coding.extensions import ExtensionRunner, ResolvedCommand
from loushang.coding.prompt import (
    PromptPreflightResult,
    preflight_user_input,
    preflight_user_input_async,
)
from loushang.coding.session.builtin_commands import (
    BuiltinCommandBackend,
    execute_builtin_command_async,
    is_builtin_command,
    list_builtin_command_descriptors,
)
from loushang.coding.session.types import (
    CommandExecutionResult,
    CommandSourceInfo,
    SessionCommandDescriptor,
)
from loushang.coding.source_info import (
    SourceDescriptor,
    source_info_from_resource_descriptor,
)
from loushang.coding.store import SessionManager
from loushang.harness.capabilities.commands import (
    CommandDispatchOutcome,
    CommandHandlerBinding,
    ParsedSlashCommand,
    dispatch_command_async,
    normalize_command_name,
    split_slash_command,
)
from loushang.harness.capabilities.packs import (
    CapabilityPack,
    CapabilityPackComposer,
)
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.harness.resources.frontmatter import strip_frontmatter
from loushang.harness.resources.source import SourceInfo as ExtensionSourceInfo
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
    SkillDescriptor,
)


@dataclass
class CommandController:
    session_manager: SessionManager
    get_extension_runner: Callable[[], ExtensionRunner | None]
    get_resource_bundle: Callable[[], ResourceBundle | None]
    get_diagnostics_service: Callable[[], DiagnosticsService | None]
    builtin_backend: BuiltinCommandBackend | None = None
    pack_composer: CapabilityPackComposer = field(
        default_factory=CapabilityPackComposer
    )

    def list_commands(self) -> list[SessionCommandDescriptor]:
        builtin_commands: list[SessionCommandDescriptor] = []
        if self.builtin_backend is not None:
            builtin_commands.extend(list_builtin_command_descriptors())

        extension_commands: list[SessionCommandDescriptor] = []
        extension_runner = self.get_extension_runner()
        if extension_runner is not None:
            for command in extension_runner.get_registered_commands():
                extension_commands.append(
                    SessionCommandDescriptor(
                        name=command.invocation_name,
                        description=command.description,
                        source="extension",
                        source_info=_command_source_info_from_extension(
                            command.source_info
                        ),
                        invocation_name=command.invocation_name,
                        conflict_group=command.name
                        if command.invocation_name != command.name
                        else None,
                    )
                )

        resource_commands: list[SessionCommandDescriptor] = []
        resource_bundle = self.get_resource_bundle()
        if resource_bundle is not None:
            for prompt in resource_bundle.prompts:
                resource_commands.append(
                    SessionCommandDescriptor(
                        name=prompt.name,
                        description=_command_description_from_prompt(prompt),
                        source="prompt",
                        source_info=source_info_from_resource_descriptor(
                            cast(SourceDescriptor, prompt)
                        ),
                        argument_hint=prompt.argument_hint,
                    )
                )
            for skill in resource_bundle.skills:
                if not skill.enabled:
                    continue
                resource_commands.append(
                    SessionCommandDescriptor(
                        name=f"skill:{skill.name}",
                        description=_command_description_from_skill(skill),
                        source="skill",
                        source_info=source_info_from_resource_descriptor(
                            cast(SourceDescriptor, skill)
                        ),
                    )
                )
        return list(
            self.pack_composer.compose(
                (
                    CapabilityPack(
                        pack_id="coding.builtin-commands",
                        source="product",
                        priority=300,
                        items=tuple(builtin_commands),
                    ),
                    CapabilityPack(
                        pack_id="coding.extension-commands",
                        source="extension",
                        priority=200,
                        items=tuple(extension_commands),
                    ),
                    CapabilityPack(
                        pack_id="coding.resource-commands",
                        source="product",
                        priority=100,
                        items=tuple(resource_commands),
                    ),
                )
            ).items
        )

    async def execute_command_async(
        self, invocation_name: str, args: str
    ) -> CommandExecutionResult | None:
        invocation_name = normalize_command_name(invocation_name)
        invocation = ParsedSlashCommand(
            name=invocation_name,
            args=args,
            is_mcp=invocation_name.endswith(" (MCP)"),
        )
        outcome = await dispatch_command_async(
            invocation,
            self.pack_composer.compose(
                (
                    CapabilityPack(
                        pack_id="coding.extension-command-handler",
                        source="extension",
                        priority=300,
                        items=(
                            CommandHandlerBinding(
                                "extension", self._dispatch_extension_command
                            ),
                        ),
                    ),
                    CapabilityPack(
                        pack_id="coding.builtin-command-handler",
                        source="product",
                        priority=200,
                        items=(
                            CommandHandlerBinding(
                                "builtin", self._dispatch_builtin_command
                            ),
                        ),
                    ),
                    CapabilityPack(
                        pack_id="coding.resource-command-handler",
                        source="product",
                        priority=100,
                        items=(
                            CommandHandlerBinding(
                                "resource", self._dispatch_resource_command
                            ),
                        ),
                    ),
                )
            ).items,
        )
        return outcome.result if outcome.handled else None

    async def _dispatch_extension_command(
        self,
        invocation: ParsedSlashCommand,
    ) -> CommandDispatchOutcome[CommandExecutionResult]:
        extension_runner = self.get_extension_runner()
        if extension_runner is not None:
            command = extension_runner.get_command(invocation.name)
            if command is not None:
                context = extension_runner.create_command_context(
                    fallback_cwd=self.session_manager.get_cwd()
                )
                try:
                    await command.handler(invocation.args, context)
                except Exception as exc:
                    self.record_extension_command_error(command=command, exc=exc)
                    return CommandDispatchOutcome.handled_result(
                        CommandExecutionResult(
                            invocation_name=command.invocation_name, result=None
                        )
                    )
                return CommandDispatchOutcome.handled_result(
                    CommandExecutionResult(
                        invocation_name=command.invocation_name, result=None
                    )
                )
        return CommandDispatchOutcome.unhandled()

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

    def _dispatch_resource_command(
        self,
        invocation: ParsedSlashCommand,
    ) -> CommandDispatchOutcome[CommandExecutionResult]:
        result = self.execute_resource_command(invocation.name, invocation.args)
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
        resource_bundle = self.get_resource_bundle()
        if resource_bundle is None:
            self.record_command_not_found(invocation_name, args)
            return None
        command_text = f"/{invocation_name}{f' {args}' if args else ''}"
        result = preflight_user_input(command_text, resource_bundle=resource_bundle)
        self.record_preflight_diagnostics(result.diagnostics)
        if result.diagnostics:
            return None
        if result.text == command_text:
            self.record_command_not_found(invocation_name, args)
            return None
        source = "skill" if invocation_name.startswith("skill:") else "prompt"
        return CommandExecutionResult(
            invocation_name=invocation_name,
            result={
                "source": source,
                "text": result.text,
            },
        )

    def record_command_not_found(self, invocation_name: str, args: str) -> None:
        diagnostics_service = self.get_diagnostics_service()
        if diagnostics_service is None:
            return
        diagnostics_service.capture_failure(
            code="command_not_found",
            error=f"Command not found: /{invocation_name}",
            phase="runtime",
            source="session",
            level="warning",
            session_id=self.session_manager.get_header().conversation_id,
            entry_id=self.session_manager.get_leaf_id(),
            details={
                "invocation_name": invocation_name,
                "args": args,
            },
        )

    async def get_command_argument_completions(
        self, invocation_name: str, prefix: str
    ) -> list[object] | None:
        extension_runner = self.get_extension_runner()
        if extension_runner is None:
            return None
        return await extension_runner.get_command_argument_completions(
            invocation_name, prefix
        )

    def extract_extension_command_invocation(
        self, user_input: str
    ) -> tuple[str, str] | None:
        extension_runner = self.get_extension_runner()
        if extension_runner is None:
            return None
        parsed = split_slash_command(user_input)
        if parsed is None:
            return None
        invocation_name, args = parsed
        if extension_runner.get_command(invocation_name) is None:
            return None
        return invocation_name, args

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
        result = preflight_user_input(
            user_input,
            resource_bundle=self.get_resource_bundle(),
        )
        self.record_preflight_diagnostics(result.diagnostics)
        return result

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
        result = await preflight_user_input_async(
            user_input,
            resource_bundle=self.get_resource_bundle(),
        )
        self.record_preflight_diagnostics(result.diagnostics)
        return result

    def record_preflight_diagnostics(
        self, diagnostics: tuple[ResourceDiagnostic, ...]
    ) -> None:
        diagnostics_service = self.get_diagnostics_service()
        if diagnostics_service is None or not diagnostics:
            return
        diagnostics_service.record_many(
            diagnostics_service.normalize_resource_diagnostic(
                diagnostic,
                phase="runtime",
                source="session",
                session_id=self.session_manager.get_header().conversation_id,
                entry_id=self.session_manager.get_leaf_id(),
            )
            for diagnostic in diagnostics
        )

    def record_extension_command_error(
        self, *, command: ResolvedCommand, exc: BaseException
    ) -> None:
        diagnostics_service = self.get_diagnostics_service()
        if diagnostics_service is None:
            return
        source_info = command.source_info
        diagnostics_service.capture_failure(
            code="extension_command_failed",
            error=exc if isinstance(exc, Exception) else str(exc),
            phase="runtime",
            source="extensions",
            session_id=self.session_manager.get_header().conversation_id,
            entry_id=self.session_manager.get_leaf_id(),
            source_path=command.source_info.path,
            details={
                "invocation_name": command.invocation_name,
                "command_name": command.name,
                "extension_name": command.extension_name,
                "source_info": {
                    "path": source_info.path.as_posix(),
                    "source": source_info.source,
                    "scope": source_info.scope,
                    "origin": source_info.origin,
                    "base_dir": source_info.base_dir.as_posix()
                    if source_info.base_dir is not None
                    else None,
                },
            },
        )


def _command_source_info_from_extension(
    source_info: ExtensionSourceInfo,
) -> CommandSourceInfo:
    return CommandSourceInfo(
        path=source_info.path.as_posix(),
        source=source_info.source,
        scope=source_info.scope,
        origin=source_info.origin,
        base_dir=source_info.base_dir.as_posix()
        if source_info.base_dir is not None
        else source_info.path.parent.as_posix(),
    )


def _command_description_from_prompt(prompt: PromptFragmentDescriptor) -> str | None:
    if isinstance(prompt.description, str) and prompt.description.strip():
        return prompt.description.strip()
    description = strip_frontmatter(prompt.text).strip()
    return description or None


def _command_description_from_skill(skill: SkillDescriptor) -> str | None:
    if isinstance(skill.description, str) and skill.description.strip():
        return skill.description.strip()
    description = strip_frontmatter(skill.content or "").strip()
    return description or None
