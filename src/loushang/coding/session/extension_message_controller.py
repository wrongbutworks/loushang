from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from loushang.agent import Agent
from loushang.ai.types import ImagePart
from loushang.harness.agent_transcript import ApplicationMessage
from loushang.harness.session import ApplicationInputRuntime, QueueController

RunPrompt = Callable[[object, list[ImagePart] | None], Awaitable[None]]


@dataclass
class ExtensionMessageController:
    agent: Agent
    queue_controller: QueueController
    application_inputs: ApplicationInputRuntime
    run_prompt: RunPrompt | None = None

    async def send_message(
        self, message: object, options: object | None = None
    ) -> None:
        if not isinstance(message, dict):
            raise TypeError("sendMessage expects a message object.")
        custom_type = message.get("customType", message.get("custom_type"))
        if not isinstance(custom_type, str) or not custom_type:
            raise ValueError("sendMessage requires customType.")
        content = message.get("content", "")
        display = bool(message.get("display", True))
        details = message.get("details")
        opts = options if isinstance(options, dict) else {}
        deliver_as = opts.get("deliverAs", opts.get("deliver_as"))
        trigger_turn = bool(opts.get("triggerTurn", opts.get("trigger_turn")))
        normalized_content = (
            content if isinstance(content, str | list) else str(content)
        )
        delivery_mode = _delivery_mode(
            deliver_as=deliver_as,
            trigger_turn=trigger_turn,
            streaming=self.agent.is_streaming,
        )
        app_message = ApplicationMessage(
            application_message_id=str(uuid4()),
            custom_type=custom_type,
            content=normalized_content,
            display=display,
            details=details,
            timestamp=datetime.now(timezone.utc).timestamp(),
            origin="extension",
            delivery_mode=delivery_mode,
        )
        await self.application_inputs.deliver(app_message)

    async def send_user_message(
        self, content: object, options: object | None = None
    ) -> None:
        text, images = _normalize_extension_user_message_content(content)
        opts = options if isinstance(options, dict) else {}
        deliver_as = opts.get("deliverAs", opts.get("deliver_as"))
        if self.agent.is_streaming:
            if deliver_as == "followUp" or deliver_as == "follow_up":
                self.queue_controller.queue_prepared_follow_up(text, images=images)
                return
            if deliver_as == "steer":
                self.queue_controller.queue_prepared_steering(text, images=images)
                return
            raise RuntimeError(
                "Agent is already processing. Specify deliverAs ('steer' or 'followUp') to queue the message."
            )
        await self._run_prompt(text, images=images)

    def has_pending_messages(self) -> bool:
        return self.application_inputs.has_pending_messages()

    async def _run_prompt(
        self,
        prompt: object,
        images: list[ImagePart] | None = None,
    ) -> None:
        if self.run_prompt is not None:
            await self.run_prompt(prompt, images)
            return
        await self.agent.prompt(prompt, images=images)  # type: ignore[arg-type]


def _normalize_extension_user_message_content(
    content: object,
) -> tuple[str, list[ImagePart] | None]:
    if isinstance(content, str):
        return content, None
    if isinstance(content, list):
        text_parts: list[str] = []
        images: list[ImagePart] = []
        for part in content:
            part_type = _content_part_type(part)
            if part_type == "text":
                text = _content_part_text(part)
                if text is not None:
                    text_parts.append(text)
                continue
            if part_type == "image":
                images.append(part)  # type: ignore[arg-type]
        return "\n".join(text_parts), images or None
    raise TypeError("sendUserMessage expects a string or content block list.")


def _content_part_type(part: object) -> str | None:
    if isinstance(part, dict):
        value = part.get("type")
        return value if isinstance(value, str) else None
    value = getattr(part, "type", None)
    return value if isinstance(value, str) else None


def _content_part_text(part: object) -> str | None:
    if isinstance(part, dict):
        value = part.get("text")
        return value if isinstance(value, str) else None
    value = getattr(part, "text", None)
    return value if isinstance(value, str) else None


def _delivery_mode(*, deliver_as: object, trigger_turn: bool, streaming: bool):
    if deliver_as in {"nextTurn", "next_turn"}:
        return "next_turn"
    if deliver_as in {"followUp", "follow_up"}:
        return "follow_up"
    if streaming:
        return "steering"
    if trigger_turn:
        return "trigger_turn"
    return "direct"
