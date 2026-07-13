from __future__ import annotations

from dataclasses import dataclass

import pytest

from loushang.agent.json_codec import (
    AgentMessageJsonCodec,
    CustomMessageJsonCodec,
    serialize_tool_result,
)
from loushang.agent.types import AgentToolResult, CustomAgentMessage
from loushang.ai.types import TextPart, UserMessage


@dataclass(frozen=True)
class NoteMessage(CustomAgentMessage):
    role: str
    text: str


def _serialize_note(message: CustomAgentMessage) -> dict[str, object]:
    assert isinstance(message, NoteMessage)
    return {"role": "note", "text": message.text}


def _deserialize_note(payload: dict[str, object]) -> CustomAgentMessage:
    return NoteMessage(role="note", text=str(payload["text"]))


def _note_registration(*, role: str = "note") -> CustomMessageJsonCodec:
    return CustomMessageJsonCodec(
        role=role,
        message_type=NoteMessage,
        serialize=_serialize_note,
        deserialize=_deserialize_note,
    )


def test_agent_message_codec_composes_ai_and_custom_messages() -> None:
    codec = AgentMessageJsonCodec([_note_registration()])
    note = NoteMessage(role="note", text="remember")
    user = UserMessage(role="user", content="hello", timestamp=1.0)

    assert codec.roles == ("note",)
    assert codec.deserialize(codec.serialize(note)) == note
    assert codec.deserialize(codec.serialize(user)) == user


def test_agent_message_codec_rejects_conflicting_registrations() -> None:
    codec = AgentMessageJsonCodec([_note_registration()])

    with pytest.raises(ValueError, match="role is already registered"):
        codec.register(_note_registration())
    with pytest.raises(ValueError, match="role must not be empty"):
        codec.register(_note_registration(role=""))


def test_agent_message_codec_rejects_unknown_messages_and_roles() -> None:
    codec = AgentMessageJsonCodec()

    with pytest.raises(ValueError, match="Unsupported custom agent message type"):
        codec.serialize(NoteMessage(role="note", text="unknown"))
    with pytest.raises(ValueError, match="Unsupported custom agent message role"):
        codec.deserialize({"role": "note", "text": "unknown"})


def test_agent_tool_result_codec_normalizes_details() -> None:
    result = AgentToolResult(
        content=[TextPart(type="text", text="ok")],
        details={"items": (1, 2)},
        terminate=True,
    )

    assert serialize_tool_result(result) == {
        "content": [{"type": "text", "text": "ok", "textSignature": None}],
        "details": {"items": [1, 2]},
        "terminate": True,
    }
