from __future__ import annotations

import asyncio

from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
from loushang.harness.agent_transcript import (
    AgentTranscriptCompactionRuntime,
    AgentTranscriptRecord,
    AgentTranscriptRetryRuntime,
    AgentTranscriptSession,
    AgentTranscriptUnitOfWork,
    CompactionPreparation,
    CompactionResult,
    TranscriptCompactionPolicy,
    build_context_usage_snapshot,
)
from loushang.harness.conversation import (
    ConversationHeader,
    ConversationKey,
    MemoryConversationStore,
)
from loushang.harness.events import ContextCompactionCompleted, RetryCompleted
from loushang.harness.runtime.retry import RetryPolicy


def _model(*, context_window: int = 100) -> Model:
    return Model(
        id="test-model",
        name="Test",
        provider="test",
        endpoint="responses",
        capabilities=Capabilities(
            context_window=context_window,
            max_tokens=64,
        ),
    )


def _usage(total_tokens: int = 0) -> Usage:
    return Usage(
        input=total_tokens,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=total_tokens,
        cost=None,
    )


def _assistant(
    *,
    text: str = "answer",
    total_tokens: int = 0,
    stop_reason: str = "stop",
    error_message: str | None = None,
    timestamp: float = 1.0,
) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="responses",
        provider="test",
        model="test-model",
        response_id=None,
        usage=_usage(total_tokens),
        stop_reason=stop_reason,
        error_message=error_message,
        timestamp=timestamp,
    )


async def _session() -> AgentTranscriptSession:
    store: MemoryConversationStore[ConversationHeader, AgentTranscriptRecord] = (
        MemoryConversationStore(record_id=lambda record: record.record_id)
    )
    transcript = await AgentTranscriptUnitOfWork.create(
        store,
        ConversationKey("test", "maintenance"),
        ConversationHeader(
            conversation_id="maintenance",
            version=1,
            created_at="2026-07-18T00:00:00Z",
        ),
        id_factory=iter(("user-1", "assistant-1", "checkpoint-1")).__next__,
    )
    return AgentTranscriptSession(transcript=transcript)


def test_context_usage_is_profile_owned_and_stales_at_checkpoint() -> None:
    async def scenario() -> None:
        session = await _session()
        user_id = await session.append_message(
            UserMessage(role="user", content="prompt", timestamp=0.0)
        )
        await session.append_message(_assistant(total_tokens=95))
        snapshot = build_context_usage_snapshot(
            session.build_context().messages,
            session.get_branch(),
            _model(),
            reserve_tokens=10,
        )
        assert snapshot.compactable is True
        assert snapshot.threshold_tokens == 90

        await session.append_compaction("summary", user_id, 95)
        stale = build_context_usage_snapshot(
            session.build_context().messages,
            session.get_branch(),
            _model(),
            reserve_tokens=10,
        )
        assert stale.stale_after_compaction is True
        assert stale.tokens is None

    asyncio.run(scenario())


def test_compaction_runtime_commits_checkpoint_and_publishes_common_events() -> None:
    async def scenario() -> None:
        session = await _session()
        user_id = await session.append_message(
            UserMessage(role="user", content="older", timestamp=0.0)
        )
        assistant_id = await session.append_message(_assistant(total_tokens=20))
        events: list[object] = []
        refreshed: list[bool] = []

        def prepare(entries, keep_recent_tokens):
            assert [entry.record_id for entry in entries] == [user_id, assistant_id]
            assert keep_recent_tokens == 4
            return CompactionPreparation(
                first_kept_entry_id=assistant_id,
                messages_to_summarize=[session.build_context().messages[0]],
                turn_prefix_messages=[],
                is_split_turn=False,
                tokens_before=20,
                details={"plan": "standard"},
            )

        async def execute(preparation, instructions):
            assert instructions == "retain decisions"
            return CompactionResult(
                summary="summary",
                first_kept_entry_id=preparation.first_kept_entry_id,
                tokens_before=preparation.tokens_before,
            )

        runtime = AgentTranscriptCompactionRuntime(
            transcript=session,
            get_policy=lambda: TranscriptCompactionPolicy(
                enabled=True,
                reserve_tokens=10,
                compact_percent=80,
                keep_recent_tokens=4,
            ),
            get_model=_model,
            get_context_messages=lambda: list(session.build_context().messages),
            refresh_context=lambda: refreshed.append(True),
            prepare_compaction=prepare,
            execute_compaction=execute,
            dispatch_event=lambda event: _append(events, event),
            has_queued_messages=lambda: False,
        )

        result = await runtime.compact(
            reason="manual",
            will_retry=False,
            custom_instructions="retain decisions",
        )

        assert result is not None
        assert session.get_entries()[-1].kind == "context.compaction_checkpoint"
        assert refreshed == [True]
        assert isinstance(events[-1], ContextCompactionCompleted)
        assert events[-1].result == {
            "summary": "summary",
            "first_kept_entry_id": assistant_id,
            "tokens_before": 20,
            "details": {"plan": "standard"},
        }

    asyncio.run(scenario())


def test_compaction_runtime_counts_the_completed_message_before_context_refresh() -> None:
    async def scenario() -> None:
        session = await _session()
        user_id = await session.append_message(
            UserMessage(role="user", content="older", timestamp=0.0)
        )
        completed = _assistant(total_tokens=95)

        def prepare(entries, keep_recent_tokens):
            assert [entry.record_id for entry in entries] == [user_id]
            assert keep_recent_tokens == 0
            return CompactionPreparation(
                first_kept_entry_id=user_id,
                messages_to_summarize=list(session.build_context().messages),
                turn_prefix_messages=[],
                is_split_turn=False,
                tokens_before=95,
            )

        async def execute(preparation, instructions):
            assert instructions is None
            return CompactionResult(
                summary="summary",
                first_kept_entry_id=preparation.first_kept_entry_id,
                tokens_before=preparation.tokens_before,
            )

        runtime = AgentTranscriptCompactionRuntime(
            transcript=session,
            get_policy=lambda: TranscriptCompactionPolicy(
                enabled=True,
                reserve_tokens=10,
            ),
            get_model=_model,
            get_context_messages=lambda: list(session.build_context().messages),
            refresh_context=lambda: None,
            prepare_compaction=prepare,
            execute_compaction=execute,
            dispatch_event=lambda event: _append([], event),
            has_queued_messages=lambda: False,
        )

        result = await runtime.maybe_compact_after_turn(
            completed,
            is_context_overflow_fn=lambda message, context_window: False,
        )

        assert result is not None
        assert session.get_entries()[-1].kind == "context.compaction_checkpoint"

    asyncio.run(scenario())


def test_retry_runtime_owns_identity_free_retry_lifecycle() -> None:
    async def scenario() -> None:
        messages = [
            _assistant(
                stop_reason="error",
                error_message="503 service unavailable",
            )
        ]
        events: list[object] = []
        continued: list[bool] = []
        runtime = AgentTranscriptRetryRuntime(
            get_policy=lambda: RetryPolicy(
                enabled=True,
                max_attempts=2,
                base_delay_ms=0,
            ),
            get_messages=lambda: list(messages),
            set_messages=lambda updated: _replace(messages, updated),
            get_context_window=lambda: 100,
            dispatch_event=lambda event: _append(events, event),
            continue_run=lambda: _append(continued, True),
            record_runtime_exception=lambda **kwargs: None,
            sleep_for_retry=lambda delay_ms, signal: _sleep(delay_ms, signal),
            is_context_overflow_fn=lambda message, context_window: False,
        )

        assert await runtime.handle_retryable_error(messages[0]) is True
        await asyncio.sleep(0)
        assert messages == []
        assert continued == [True]
        await runtime.finish(success=True, attempt=1)
        assert isinstance(events[-1], RetryCompleted)
        assert runtime.is_retrying is False

    asyncio.run(scenario())


async def _append(values: list[object], value: object) -> None:
    values.append(value)


def _replace(target: list[object], replacement: list[object]) -> None:
    target[:] = replacement


async def _sleep(delay_ms: int, signal: object) -> None:
    del delay_ms, signal
