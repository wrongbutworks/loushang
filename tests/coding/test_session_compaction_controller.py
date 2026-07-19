from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
from loushang.coding.compaction import CompactionResult
from loushang.coding.control import CompactionSettings
from loushang.coding.session.compaction_controller import CompactionController
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
    create_agent_transcript_compaction_capability,
)


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
        assert "api_key" not in kwargs
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
    from loushang.harness.events import (
        ContextCompactionCompleted,
        ContextCompactionStarted,
    )

    started = events[0]
    completed = events[-1]
    assert isinstance(started, ContextCompactionStarted)
    assert started.usage is not None
    assert started.reason == "manual"
    assert started.usage["compact_percent"] == 80
    assert started.usage["reserve_tokens"] == 8192
    assert started.usage["keep_recent_tokens"] == 1
    assert started.usage["threshold_reason"] == "compact_percent"

    assert isinstance(completed, ContextCompactionCompleted)
    assert completed.reason == "manual"
    assert completed.result == {
        "summary": "controller summary",
        "first_kept_entry_id": assistant_id,
        "tokens_before": result.tokens_before,
        "details": compaction_entry.payload.details,
    }
    assert completed.aborted is False
    assert completed.will_retry is False
    assert completed.usage_before == started.usage
    assert completed.usage_after is not None
    assert completed.usage_after["tokens"] is None
    assert completed.usage_after["percent"] is None
    assert completed.usage_after["stale_after_compaction"] is True


def test_compaction_controller_uses_selected_capability_policy_without_override(
    tmp_path,
) -> None:
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
    agent = Agent(
        initial_state={"system_prompt": "", "model": _model(), "thinking_level": "off"}
    )

    async def _dispatch_event(event: object) -> None:
        del event

    controller = CompactionController(
        agent=agent,
        session_manager=manager,
        get_settings=CompactionSettings,
        get_extension_runner=lambda: None,
        dispatch_event=_dispatch_event,
        compaction_capability=create_agent_transcript_compaction_capability(
            implementation=TURN_AWARE_SUMMARY_IMPLEMENTATION,
            implementation_version=TURN_AWARE_SUMMARY_VERSION,
            config={
                "enabled": False,
                "compactPercent": 75.0,
                "reserveTokens": 4_096,
                "keepRecentTokens": 2_048,
            },
        ),
    )

    policy = controller._runtime._get_policy()

    assert policy.enabled is False
    assert policy.compact_percent == 75.0
    assert policy.reserve_tokens == 4_096
    assert policy.keep_recent_tokens == 2_048
