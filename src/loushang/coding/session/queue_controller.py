from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from loushang.agent import Agent
from loushang.ai.types import ImagePart, TextPart, UserMessage
from loushang.observability import get_log


PreflightUserInput = Callable[[str], object]
RejectExtensionCommand = Callable[[str], None]
QueueUpdateEmitter = Callable[[], None]
QueueKind = Literal["steering", "follow_up"]

log = get_log(__name__).bind(component="QueueController")


@dataclass(frozen=True)
class QueuedMessageSnapshot:
    id: str
    kind: QueueKind
    text: str


@dataclass(frozen=True)
class QueueSnapshot:
    steering: tuple[QueuedMessageSnapshot, ...] = ()
    follow_up: tuple[QueuedMessageSnapshot, ...] = ()


@dataclass(frozen=True)
class _QueuedMessage:
    id: str
    kind: QueueKind
    visible_text: str
    message_identity: int


@dataclass
class QueueController:
    agent: Agent
    preflight_user_input: PreflightUserInput
    reject_extension_command: RejectExtensionCommand
    emit_queue_update: QueueUpdateEmitter
    _steering_messages: list[_QueuedMessage] = field(default_factory=list)
    _follow_up_messages: list[_QueuedMessage] = field(default_factory=list)
    _next_turn_messages: list[object] = field(default_factory=list)
    _next_queue_id: int = 1

    @property
    def pending_message_count(self) -> int:
        return len(self._steering_messages) + len(self._follow_up_messages)

    def get_steering_messages(self) -> list[str]:
        return [message.visible_text for message in self._steering_messages]

    def get_follow_up_messages(self) -> list[str]:
        return [message.visible_text for message in self._follow_up_messages]

    def get_queue_snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            steering=tuple(_snapshot(message) for message in self._steering_messages),
            follow_up=tuple(_snapshot(message) for message in self._follow_up_messages),
        )

    def append_next_turn_message(self, message: object) -> None:
        self._next_turn_messages.append(message)

    def drain_next_turn_messages(self) -> list[object]:
        messages = list(self._next_turn_messages)
        self._next_turn_messages.clear()
        return messages

    def has_pending_messages(self) -> bool:
        return bool(self._steering_messages or self._follow_up_messages or self.agent.has_queued_messages())

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
        item = self._queue_item(kind="steering", visible_text=visible_text, message=queued_message)
        self._steering_messages.append(item)
        _debug_queue_event("queue.message_queued", item)
        self.emit_queue_update()

    def queue_follow_up_message(self, visible_text: str, message: object) -> None:
        queued_message = self.agent.follow_up(message)
        item = self._queue_item(kind="follow_up", visible_text=visible_text, message=queued_message)
        self._follow_up_messages.append(item)
        _debug_queue_event("queue.message_queued", item)
        self.emit_queue_update()

    def clear_queue(self) -> dict[str, list[str]]:
        steering = self.get_steering_messages()
        follow_up = self.get_follow_up_messages()
        self._steering_messages.clear()
        self._follow_up_messages.clear()
        self.agent.clear_all_queues()
        log.debug_event("agent", "queue.cleared", steering=len(steering), follow_up=len(follow_up))
        self.emit_queue_update()
        return {"steering": steering, "followUp": follow_up, "follow_up": follow_up}

    def mark_message_consumed(self, message: object) -> bool:
        message_identity = id(message)
        consumed = _pop_first_match(self._steering_messages, lambda item: item.message_identity == message_identity)
        if consumed is not None:
            _debug_queue_event("queue.message_consumed", consumed)
            self.emit_queue_update()
            return True
        consumed = _pop_first_match(self._follow_up_messages, lambda item: item.message_identity == message_identity)
        if consumed is not None:
            _debug_queue_event("queue.message_consumed", consumed)
            self.emit_queue_update()
            return True
        text = _visible_message_text(message)
        if not text:
            return False
        consumed = _pop_first_match(self._steering_messages, lambda item: item.visible_text == text)
        if consumed is not None:
            _debug_queue_event("queue.message_consumed", consumed)
            self.emit_queue_update()
            return True
        consumed = _pop_first_match(self._follow_up_messages, lambda item: item.visible_text == text)
        if consumed is not None:
            _debug_queue_event("queue.message_consumed", consumed)
            self.emit_queue_update()
            return True
        return False

    def _queue_item(self, *, kind: QueueKind, visible_text: str, message: object) -> _QueuedMessage:
        item = _QueuedMessage(
            id=f"q{self._next_queue_id}",
            kind=kind,
            visible_text=visible_text,
            message_identity=id(message),
        )
        self._next_queue_id += 1
        return item

    def prepare_continue_run(self) -> bool:
        last_message = self.agent.state.messages[-1] if self.agent.state.messages else None
        if getattr(last_message, "role", None) != "assistant":
            return False
        if self._steering_messages:
            _drain_local_queue(self._steering_messages, self.agent.steering_mode)
            return True
        if self._follow_up_messages:
            _drain_local_queue(self._follow_up_messages, self.agent.follow_up_mode)
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


def _snapshot(message: _QueuedMessage) -> QueuedMessageSnapshot:
    return QueuedMessageSnapshot(id=message.id, kind=message.kind, text=message.visible_text)


def _pop_first_match(messages: list[_QueuedMessage], predicate: Callable[[_QueuedMessage], bool]) -> _QueuedMessage | None:
    for index, message in enumerate(messages):
        if predicate(message):
            return messages.pop(index)
    return None


def _debug_queue_event(name: str, item: _QueuedMessage) -> None:
    log.debug_event("agent", name, id=item.id, kind=item.kind, text_len=len(item.visible_text))


def _drain_local_queue(queue: list[_QueuedMessage], mode: str) -> list[_QueuedMessage]:
    if mode == "all":
        drained = list(queue)
        queue.clear()
        return drained
    if not queue:
        return []
    return [queue.pop(0)]
