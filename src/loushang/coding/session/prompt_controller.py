from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from loushang.ai.types import ImagePart, TextPart, UserMessage
from loushang.coding.message import create_custom_message

CommandExtractor = Callable[[str], tuple[str, str] | None]
CommandExecutor = Callable[[str, str], Awaitable[object | None]]
ExtensionRunnerProvider = Callable[[], object | None]
CwdProvider = Callable[[], str]
Preflight = Callable[..., Awaitable[object]]
BeforeAgentStartOptions = Callable[[], dict[str, object]]
ExtensionDiagnosticsSync = Callable[..., None]
PrePromptCompaction = Callable[[], Awaitable[object | None]]
RunPrompt = Callable[[list[object]], Awaitable[None]]


class AgentPort(Protocol):
    is_streaming: bool
    state: object

    @property
    def system_prompt(self) -> str: ...

    async def prompt(self, messages: list[object]) -> None: ...


class QueuePort(Protocol):
    def queue_prepared_follow_up(self, text: str, images: list[ImagePart] | None = None) -> None: ...

    def queue_prepared_steering(self, text: str, images: list[ImagePart] | None = None) -> None: ...

    def drain_next_turn_messages(self) -> list[object]: ...


@dataclass
class PromptController:
    agent: AgentPort
    queue_controller: QueuePort
    get_extension_runner: ExtensionRunnerProvider
    get_cwd: CwdProvider
    extract_extension_command_invocation: CommandExtractor
    execute_command_async: CommandExecutor
    preflight_user_input_async: Preflight
    before_agent_start_system_prompt_options: BeforeAgentStartOptions
    sync_extension_diagnostics: ExtensionDiagnosticsSync
    compact_before_prompt_async: PrePromptCompaction | None = None
    run_prompt: RunPrompt | None = None

    async def prompt(
        self,
        user_input: str,
        images: list[ImagePart] | None = None,
        *,
        streaming_behavior: str | None = None,
        source: str | None = None,
        preflight_result: Callable[[bool], None] | None = None,
    ) -> None:
        try:
            command = self.extract_extension_command_invocation(user_input)
            if command is not None:
                invocation_name, args = command
                await self.execute_command_async(invocation_name, args)
                if preflight_result is not None:
                    preflight_result(True)
                return
            current_input = user_input
            current_images = images
            extension_runner = self.get_extension_runner()
            if extension_runner is not None and extension_runner.has_handlers("input"):
                input_result = await extension_runner.emit_input(
                    current_input,
                    current_images,
                    source=source or "interactive",
                    cwd=self.get_cwd(),
                )
                if input_result.action == "handled":
                    if preflight_result is not None:
                        preflight_result(True)
                    return
                if input_result.action == "transform":
                    if input_result.text is not None:
                        current_input = input_result.text
                    if input_result.images is not None:
                        current_images = input_result.images
            preflight = await self.preflight_user_input_async(current_input, allow_extension_commands=False)
            if preflight.consumed:
                if preflight_result is not None:
                    preflight_result(True)
                return
            prepared_input = preflight.text
            if self.agent.is_streaming:
                if streaming_behavior in {"followUp", "follow_up"}:
                    self.queue_controller.queue_prepared_follow_up(prepared_input, images=current_images)
                elif streaming_behavior == "steer":
                    self.queue_controller.queue_prepared_steering(prepared_input, images=current_images)
                else:
                    raise RuntimeError(
                        "Agent is already processing. Specify streaming_behavior ('steer' or 'followUp') to queue the message."
                    )
                if preflight_result is not None:
                    preflight_result(True)
                return
            if self.compact_before_prompt_async is not None:
                await self.compact_before_prompt_async()
            pending_next_turn_messages = self.queue_controller.drain_next_turn_messages()
            queued_messages = [_user_message(prepared_input, images=current_images)]
            queued_messages.extend(pending_next_turn_messages)
            if extension_runner is not None:
                before_result = await extension_runner.emit_before_agent_start(
                    prompt=prepared_input,
                    images=current_images,
                    system_prompt=self.agent.system_prompt,
                    system_prompt_options=self.before_agent_start_system_prompt_options(),
                    cwd=self.get_cwd(),
                )
                if before_result is not None:
                    if before_result.system_prompt is not None:
                        self.agent.state.system_prompt = before_result.system_prompt
                    if before_result.extra_messages:
                        queued_messages.extend(_custom_messages_from_extension(before_result.extra_messages))
                self.sync_extension_diagnostics(phase="runtime")
        except Exception:
            if preflight_result is not None:
                preflight_result(False)
            raise
        if preflight_result is not None:
            preflight_result(True)
        if self.run_prompt is not None:
            await self.run_prompt(queued_messages)
        else:
            await self.agent.prompt(queued_messages)


def _user_message(text: str, images: list[ImagePart] | None = None) -> UserMessage:
    content: list[TextPart | ImagePart] = [TextPart(type="text", text=text)]
    if images:
        content.extend(images)
    return UserMessage(
        role="user",
        content=content,
        timestamp=0.0,
    )


def _custom_messages_from_extension(messages: list[object]) -> list[object]:
    custom_messages: list[object] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        custom_type = message.get("customType", message.get("custom_type"))
        if not isinstance(custom_type, str) or not custom_type:
            continue
        content = message.get("content", "")
        normalized_content = content if isinstance(content, str | list) else str(content)
        custom_messages.append(
            create_custom_message(
                custom_type=custom_type,
                content=normalized_content,
                display=bool(message.get("display", True)),
                details=message.get("details"),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
    return custom_messages
