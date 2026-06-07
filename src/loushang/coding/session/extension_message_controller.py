from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from loushang.agent import Agent
from loushang.ai.types import ImagePart
from loushang.coding.event import AgentSessionEvent
from loushang.coding.message import create_custom_message
from loushang.coding.session.queue_controller import QueueController
from loushang.coding.store import SessionManager

EventDispatcher = Callable[[AgentSessionEvent], Awaitable[None]]


@dataclass
class ExtensionMessageController:
    agent: Agent
    session_manager: SessionManager
    queue_controller: QueueController
    dispatch_event: EventDispatcher

    async def send_message(self, message: object, options: object | None = None) -> None:
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
        normalized_content = content if isinstance(content, str | list) else str(content)
        app_message = create_custom_message(
            custom_type=custom_type,
            content=normalized_content,
            display=display,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        if deliver_as in {"nextTurn", "next_turn"}:
            self.queue_controller.append_next_turn_message(app_message)
            return
        if self.agent.is_streaming:
            if deliver_as == "followUp" or deliver_as == "follow_up":
                self.queue_controller.queue_follow_up_message(_custom_message_text(app_message), app_message)
            else:
                self.queue_controller.queue_steering_message(_custom_message_text(app_message), app_message)
            return
        if trigger_turn:
            await self._send_message_async(app_message)
            return
        self.session_manager.append_custom_message_entry(
            custom_type=custom_type,
            content=normalized_content,
            display=display,
            details=details,
        )
        session_context = self.session_manager.build_session_context()
        self.agent.state.set_messages(session_context.messages)
        await self.dispatch_event({"type": "message_start", "message": app_message})
        await self.dispatch_event({"type": "message_end", "message": app_message})

    async def send_user_message(self, content: object, options: object | None = None) -> None:
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
        await self.agent.prompt(text, images=images)

    def has_pending_messages(self) -> bool:
        return self.queue_controller.has_pending_messages()

    async def _send_message_async(self, app_message) -> None:
        await self.agent.prompt(app_message)


def _normalize_extension_user_message_content(content: object) -> tuple[str, list[ImagePart] | None]:
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


def _custom_message_text(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts: list[str] = []
        has_non_text = False
        for part in content:
            part_type = _content_part_type(part)
            if part_type == "text":
                text = _content_part_text(part)
                if text:
                    text_parts.append(text)
            else:
                has_non_text = True
        if text_parts:
            return "\n".join(text_parts)
        if has_non_text:
            return "[image]"
    return str(content)
