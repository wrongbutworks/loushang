from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
from loushang.coding.compaction import CompactionResult
from loushang.coding.control import CompactionSettings
from loushang.coding.session.compaction_controller import CompactionController
from loushang.coding.store import SessionManager


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
        capabilities=Capabilities(context_window=128000, max_tokens=4096),
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


def test_compaction_controller_appends_compaction_and_rebuilds_agent_context(
    tmp_path,
) -> None:
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
    asyncio.run(
        manager.append_message(
            UserMessage(
                role="user",
                content=[
                    TextPart(type="text", text="older context that should be compacted")
                ],
                timestamp=0.0,
            )
        )
    )
    assistant_id = asyncio.run(
        manager.append_message(_assistant_text_message("recent reply"))
    )
    agent = Agent(
        initial_state={"system_prompt": "", "model": _model(), "thinking_level": "off"}
    )
    agent.state.set_messages(manager.build_session_context().messages)
    events: list[object] = []

    async def _dispatch_event(event: object) -> None:
        events.append(event)

    async def _fake_compact(**kwargs):
        preparation = kwargs["preparation"]
        assert preparation.first_kept_entry_id == assistant_id
        return CompactionResult(
            summary="controller summary",
            first_kept_entry_id=preparation.first_kept_entry_id,
            tokens_before=preparation.tokens_before,
            details=preparation.details,
        )

    controller = CompactionController(
        agent=agent,
        session_manager=manager,
        get_settings=lambda: CompactionSettings(
            enabled=True,
            compact_percent=80,
            reserve_tokens=8192,
            keep_recent_tokens=1,
        ),
        get_extension_runner=lambda: None,
        dispatch_event=_dispatch_event,
    )

    result = asyncio.run(
        controller.compact(reason="manual", will_retry=False, compact_fn=_fake_compact)
    )

    assert result.summary == "controller summary"
    assert [entry.kind for entry in manager.get_entries()] == [
        "agent.message",
        "agent.message",
        "context.compaction_checkpoint",
    ]
    compaction_entry = manager.get_entries()[-1]
    assert isinstance(compaction_entry.payload.details, dict)
    assert (
        compaction_entry.payload.details["compactionPlan"]["firstKeptEntryId"]
        == assistant_id
    )
    assert (
        compaction_entry.payload.details["compactionPlan"]["summarizedEntryIds"] == []
    )
    assert compaction_entry.payload.details["compactionPlan"]["turnPrefixEntryIds"] == [
        manager.get_entries()[0].record_id
    ]
    assert compaction_entry.payload.details["compactionPlan"]["keptEntryIds"] == [
        assistant_id
    ]
    assert compaction_entry.payload.details["compactionPlan"]["isSplitTurn"] is True
    assert compaction_entry.payload.details["compactionPlan"]["keepRecentTokens"] == 1
    assert [getattr(message, "role", None) for message in agent.state.messages] == [
        "user",
        "assistant",
    ]
    assert controller.is_compacting is False
    assert events[0]["type"] == "compaction_start"
    assert events[0]["reason"] == "manual"
    assert events[0]["usage"]["compact_percent"] == 80
    assert events[0]["usage"]["reserve_tokens"] == 8192
    assert events[0]["usage"]["keep_recent_tokens"] == 1
    assert events[0]["usage"]["threshold_reason"] == "compact_percent"

    assert events[-1]["type"] == "compaction_end"
    assert events[-1]["reason"] == "manual"
    assert events[-1]["result"] == {
        "summary": "controller summary",
        "first_kept_entry_id": assistant_id,
        "tokens_before": result.tokens_before,
        "details": compaction_entry.payload.details,
    }
    assert events[-1]["aborted"] is False
    assert events[-1]["will_retry"] is False
    assert events[-1]["usage_before"] == events[0]["usage"]
    assert events[-1]["usage_after"]["tokens"] is None
    assert events[-1]["usage_after"]["percent"] is None
    assert events[-1]["usage_after"]["stale_after_compaction"] is True
