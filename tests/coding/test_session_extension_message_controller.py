from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from loushang.agent import Agent
from loushang.ai.types import TextPart
from loushang.coding.session.extension_message_controller import ExtensionMessageController
from loushang.coding.session.queue_controller import QueueController
from loushang.coding.store import SessionManager


def _preflight(text: str):
    return SimpleNamespace(consumed=False, text=text)


def _queue_controller(agent: Agent, queue_updates: list[tuple[list[str], list[str]]]) -> QueueController:
    controller = QueueController(
        agent=agent,
        preflight_user_input=_preflight,
        reject_extension_command=lambda text: None,
        emit_queue_update=lambda: queue_updates.append(
            (controller.get_steering_messages(), controller.get_follow_up_messages())
        ),
    )
    return controller


def test_extension_message_controller_persists_custom_message_and_emits_events(tmp_path) -> None:
    agent = Agent()
    queue_updates: list[tuple[list[str], list[str]]] = []
    events: list[tuple[str, str]] = []

    async def _dispatch(event):
        events.append((event["type"], event["message"].custom_type))

    controller = ExtensionMessageController(
        agent=agent,
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        queue_controller=_queue_controller(agent, queue_updates),
        dispatch_event=_dispatch,
    )

    asyncio.run(
        controller.send_message(
            {
                "customType": "demo_notice",
                "content": "visible note",
                "display": True,
                "details": {"source": "sdk"},
            }
        )
    )

    assert [message.role for message in agent.state.messages] == ["custom"]
    assert agent.state.messages[0].custom_type == "demo_notice"
    assert events == [("message_start", "demo_notice"), ("message_end", "demo_notice")]
    assert queue_updates == []


def test_extension_message_controller_queues_streaming_messages_by_deliver_as(tmp_path) -> None:
    agent = Agent()
    agent.state.is_streaming = True
    queue_updates: list[tuple[list[str], list[str]]] = []
    controller = ExtensionMessageController(
        agent=agent,
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        queue_controller=_queue_controller(agent, queue_updates),
        dispatch_event=lambda event: None,
    )

    asyncio.run(controller.send_message({"customType": "note", "content": "custom follow"}, {"deliverAs": "followUp"}))
    asyncio.run(controller.send_user_message("queued steer", {"deliverAs": "steer"}))

    assert controller.has_pending_messages() is True
    assert controller.queue_controller.get_steering_messages() == ["queued steer"]
    assert controller.queue_controller.get_follow_up_messages() == ["custom follow"]
    assert queue_updates == [([], ["custom follow"]), (["queued steer"], ["custom follow"])]


def test_extension_message_controller_validates_streaming_user_message_deliver_as(tmp_path) -> None:
    agent = Agent()
    agent.state.is_streaming = True
    queue_updates: list[tuple[list[str], list[str]]] = []
    controller = ExtensionMessageController(
        agent=agent,
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        queue_controller=_queue_controller(agent, queue_updates),
        dispatch_event=lambda event: None,
    )

    with pytest.raises(RuntimeError, match="Specify deliverAs"):
        asyncio.run(controller.send_user_message([TextPart(type="text", text="queued")]))
