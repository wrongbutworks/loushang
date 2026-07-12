from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from loushang.agent import Agent
from loushang.ai.types import ImagePart, TextPart, UserMessage
from loushang.harness.host.queue import HostInputQueue
from loushang.harness.host.types import (
    QueuedMessageSnapshot,
    QueueMode,
    QueueSnapshot,
)
from loushang.observability import get_log

PreflightUserInput = Callable[[str], object]
RejectExtensionCommand = Callable[[str], None]
QueueUpdateEmitter = Callable[[], None]

log = get_log(__name__).bind(component="QueueController")


@dataclass
class QueueController:
    agent: Agent
    preflight_user_input: PreflightUserInput
    reject_extension_command: RejectExtensionCommand
    emit_queue_update: QueueUpdateEmitter
    _queue: HostInputQueue[object] = field(
        default_factory=HostInputQueue,
        init=False,
        repr=False,
    )

    @property
    def pending_message_count(self) -> int:
        return self._queue.pending_count

    def get_steering_messages(self) -> list[str]:
        return self._queue.texts("steering")

    def get_follow_up_messages(self) -> list[str]:
        return self._queue.texts("follow_up")

    def get_queue_snapshot(self) -> QueueSnapshot:
        return self._queue.snapshot()

    def append_next_turn_message(self, message: object) -> None:
        self._queue.append_next_turn(message)

    def drain_next_turn_messages(self) -> list[object]:
        return self._queue.drain_next_turn()

    def has_pending_messages(self) -> bool:
        return self._queue.has_pending() or self.agent.has_queued_messages()

    def steer(self, user_input: str, images: list[ImagePart] | None = None) -> None:
        self.reject_extension_command(user_input)
        preflight = self.preflight_user_input(user_input)
        if getattr(preflight, "consumed", False):
            return
        self.queue_prepared_steering(str(getattr(preflight, "text")), images=images)

    def follow_up(self, user_input: str, images: list[ImagePart] | None = None) -> None:
        self.reject_extension_command(user_input)
        preflight = self.preflight_user_input(user_input)
        if getattr(preflight, "consumed", False):
            return
        self.queue_prepared_follow_up(str(getattr(preflight, "text")), images=images)

    def queue_prepared_steering(self, text: str, images: list[ImagePart] | None = None) -> None:
        self.queue_steering_message(text, _user_message(text, images=images))

    def queue_prepared_follow_up(self, text: str, images: list[ImagePart] | None = None) -> None:
        self.queue_follow_up_message(text, _user_message(text, images=images))

    def queue_steering_message(self, visible_text: str, message: object) -> None:
        queued_message = self.agent.steer(message)
        item = self._queue.enqueue(
            "steering",
            text=visible_text,
            payload=queued_message,
        )
        _debug_queue_event("queue.message_queued", item)
        self.emit_queue_update()

    def queue_follow_up_message(self, visible_text: str, message: object) -> None:
        queued_message = self.agent.follow_up(message)
        item = self._queue.enqueue(
            "follow_up",
            text=visible_text,
            payload=queued_message,
        )
        _debug_queue_event("queue.message_queued", item)
        self.emit_queue_update()

    def clear_queue(self) -> dict[str, list[str]]:
        steering = self.get_steering_messages()
        follow_up = self.get_follow_up_messages()
        self._queue.clear()
        self.agent.clear_all_queues()
        log.debug_event("agent", "queue.cleared", steering=len(steering), follow_up=len(follow_up))
        self.emit_queue_update()
        return {"steering": steering, "followUp": follow_up, "follow_up": follow_up}

    def mark_message_consumed(self, message: object) -> bool:
        consumed = self._queue.consume(
            message,
            fallback_text=_visible_message_text(message),
        )
        if consumed is None:
            return False
        _debug_queue_event("queue.message_consumed", consumed)
        self.emit_queue_update()
        return True

    def prepare_continue_run(self) -> bool:
        last_message = self.agent.state.messages[-1] if self.agent.state.messages else None
        if getattr(last_message, "role", None) != "assistant":
            return False
        if self._queue.texts("steering"):
            self._queue.drain(
                "steering",
                cast(QueueMode, self.agent.steering_mode),
            )
            return True
        if self._queue.texts("follow_up"):
            self._queue.drain(
                "follow_up",
                cast(QueueMode, self.agent.follow_up_mode),
            )
            return True
        return False


def _user_message(text: str, images: list[ImagePart] | None = None) -> UserMessage:
    content: list[TextPart | ImagePart] = [TextPart(type="text", text=text)]
    if images:
        content.extend(images)
    return UserMessage(role="user", content=content, timestamp=0.0)


def _visible_message_text(message: object) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(_content_part_text(part) or "" for part in content if _content_part_type(part) == "text")
    return ""


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


def _debug_queue_event(name: str, item: QueuedMessageSnapshot) -> None:
    log.debug_event("agent", name, id=item.id, kind=item.kind, text_len=len(item.text))
