from __future__ import annotations

import asyncio

from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage


def _usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost={},
    )


def _model() -> Model:
    return Model(
        id="faux-model",
        name="Faux",
        provider="faux",
        endpoint="anthropic-messages",
        capabilities=Capabilities(
            reasoning=True,
            input=("text",),
            context_window=128000,
            max_tokens=4096,
        ),
    )


def _assistant_text_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


def test_tree_controller_navigates_to_user_message_parent_and_returns_editor_text(tmp_path) -> None:
    from loushang.agent import Agent
    from loushang.coding.session.tree_controller import TreeController
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    manager.append_message(UserMessage(role="user", content=[TextPart(type="text", text="root")], timestamp=0.0))
    assistant1_id = manager.append_message(_assistant_text_message("reply 1"))
    user2_id = manager.append_message(
        UserMessage(role="user", content=[TextPart(type="text", text="draft follow up")], timestamp=0.0)
    )
    manager.append_message(_assistant_text_message("reply 2"))
    agent = Agent(initial_state={"system_prompt": "", "model": _model(), "thinking_level": "off"})
    agent.state.set_messages(manager.build_session_context().messages)
    events: list[object] = []

    async def _dispatch_event(event: object) -> None:
        events.append(event)

    controller = TreeController(
        agent=agent,
        session_manager=manager,
        dispatch_event=_dispatch_event,
    )

    result = asyncio.run(controller.navigate_tree(user2_id))

    assert result.cancelled is False
    assert result.editor_text == "draft follow up"
    assert manager.get_leaf_id() == assistant1_id
    assert [getattr(message, "role", None) for message in agent.state.messages] == ["user", "assistant"]
    assert events == []
