from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from loushang.agent import Agent
from loushang.coding.compaction import estimate_context_tokens
from loushang.coding.session.context_usage import build_context_usage_snapshot
from loushang.coding.session.types import (
    AgentSessionState,
    ContextUsage,
    ModelSelection,
    SessionStats,
)
from loushang.coding.session.usage_payload import serialize_context_usage_payload
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    AgentTranscriptInspector,
    AgentTranscriptRecord,
    ContextCompactionCheckpoint,
)
from loushang.harness.host.types import RunState


@dataclass
class SessionViewController:
    agent: Agent
    session_manager: SessionManager
    get_active_tool_names: Callable[[], list[str]]
    is_retrying: Callable[[], bool]
    is_compacting: Callable[[], bool]
    get_last_diagnostics: Callable[[int], list[object]]
    get_model_selection: Callable[[], ModelSelection | None]
    is_host_running: Callable[[], bool] | None = None
    get_compaction_reserve_tokens: Callable[[], int] = lambda: 0
    get_compaction_compact_percent: Callable[[], float] = lambda: 100.0
    get_compaction_keep_recent_tokens: Callable[[], int | None] = lambda: None
    _inspector: AgentTranscriptInspector = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._inspector = AgentTranscriptInspector(self.session_manager)

    def get_state(
        self, *, steering: list[str], follow_up: list[str]
    ) -> AgentSessionState:
        is_running = (
            self.is_host_running()
            if self.is_host_running is not None
            else self.agent.state.is_streaming
        )
        return AgentSessionState(
            run=RunState(status="running" if is_running else "idle"),
            steering=steering,
            follow_up=follow_up,
            active_tool_names=self.get_active_tool_names(),
            is_compacting=self.is_compacting(),
            is_retrying=self.is_retrying(),
            thinking_level=self.agent.thinking_level,
            model_selection=self.get_model_selection(),
        )

    def get_context_usage(self) -> ContextUsage | None:
        session_context = self.session_manager.build_session_context()
        messages = list(session_context.messages)
        branch_entries: list[object] = list(self.session_manager.get_branch())
        counts = self._inspector.message_counts()

        estimated_context_tokens = (
            estimate_context_tokens(messages).tokens if messages else 0
        )
        snapshot = build_context_usage_snapshot(
            messages,
            branch_entries,
            self.agent.model,
            reserve_tokens=self.get_compaction_reserve_tokens(),
            compact_percent=self.get_compaction_compact_percent(),
            keep_recent_tokens=self.get_compaction_keep_recent_tokens(),
        )
        return ContextUsage(
            message_count=counts.message_count,
            assistant_message_count=counts.assistant_message_count,
            user_message_count=counts.user_message_count,
            tool_call_count=counts.tool_call_count,
            tool_result_count=counts.tool_result_count,
            custom_message_count=counts.application_message_count,
            estimated_context_tokens=estimated_context_tokens,
            has_compaction=self._inspector.has_compaction_checkpoint(),
            branch_depth=len(branch_entries),
            leaf_entry_id=self.session_manager.get_leaf_id(),
            tokens=snapshot.tokens,
            context_window=snapshot.context_window,
            percent=snapshot.percent,
            reserve_tokens=snapshot.reserve_tokens,
            compact_percent=snapshot.compact_percent,
            keep_recent_tokens=snapshot.keep_recent_tokens,
            percent_threshold_tokens=snapshot.percent_threshold_tokens,
            reserve_threshold_tokens=snapshot.reserve_threshold_tokens,
            threshold_tokens=snapshot.threshold_tokens,
            threshold_reason=snapshot.threshold_reason,
            source=snapshot.source,
            last_usage_index=snapshot.last_usage_index,
            stale_after_compaction=snapshot.stale_after_compaction,
            compactable=snapshot.compactable,
            reason=snapshot.reason,
        )

    def build_session_stats(self) -> SessionStats:
        entries = self.session_manager.get_entries()
        context_usage = self.get_context_usage()
        record = self.session_manager.get_session_record()
        counts = self._inspector.message_counts()
        return SessionStats(
            session_id=record.session_id,
            session_name=record.metadata.name,
            entry_count=len(entries),
            message_count=context_usage.message_count
            if context_usage is not None
            else 0,
            custom_message_count=counts.application_message_count,
            active_tool_count=len(self.get_active_tool_names()),
            is_retrying=self.is_retrying(),
            is_compacting=self.is_compacting(),
            has_diagnostics=bool(self.get_last_diagnostics(1)),
            branch_count=self._inspector.branch_leaf_count(),
            last_model_selection=self.get_model_selection(),
            context_usage=context_usage,
        )

    def get_pi_style_stats(self) -> dict[str, object]:
        user_messages = 0
        assistant_messages = 0
        tool_results = 0
        tool_calls = 0
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_write = 0
        total_cost = 0.0
        messages = list(self.agent.state.messages)
        for message in messages:
            role = getattr(message, "role", None)
            if role == "user":
                user_messages += 1
            elif role == "assistant":
                assistant_messages += 1
                content = getattr(message, "content", [])
                if isinstance(content, list):
                    tool_calls += sum(
                        1
                        for block in content
                        if getattr(block, "type", None) == "toolCall"
                    )
                usage = getattr(message, "usage", None)
                if usage is not None:
                    total_input += int(getattr(usage, "input", 0) or 0)
                    total_output += int(getattr(usage, "output", 0) or 0)
                    total_cache_read += int(getattr(usage, "cache_read", 0) or 0)
                    total_cache_write += int(getattr(usage, "cache_write", 0) or 0)
                    cost = getattr(usage, "cost", {})
                    if isinstance(cost, dict):
                        total_cost += float(
                            cost.get(
                                "total",
                                sum(
                                    value
                                    for value in cost.values()
                                    if isinstance(value, int | float)
                                ),
                            )
                        )
            elif role == "toolResult":
                tool_results += 1
        session_file = self.session_manager.get_session_file()
        return {
            "sessionFile": str(session_file) if session_file is not None else None,
            "sessionId": self.session_manager.get_session_record().session_id,
            "userMessages": user_messages,
            "assistantMessages": assistant_messages,
            "toolCalls": tool_calls,
            "toolResults": tool_results,
            "totalMessages": len(messages),
            "tokens": {
                "input": total_input,
                "output": total_output,
                "cacheRead": total_cache_read,
                "cacheWrite": total_cache_write,
                "total": total_input
                + total_output
                + total_cache_read
                + total_cache_write,
            },
            "cost": total_cost,
            "contextUsage": serialize_context_usage_payload(self.get_context_usage()),
            "latestCompaction": _latest_compaction_payload(
                self.session_manager.get_branch()
            ),
        }

    def get_user_messages_for_forking(self) -> list[dict[str, str]]:
        return [
            {"entry_id": candidate.record_id, "text": candidate.text}
            for candidate in self._inspector.fork_candidates()
        ]

    def get_pi_style_user_messages_for_forking(self) -> list[dict[str, str]]:
        return [
            {"entryId": message["entry_id"], "text": message["text"]}
            for message in self.get_user_messages_for_forking()
        ]

    def get_entry_text(self, entry_id: str) -> str | None:
        return self._inspector.entry_text(entry_id)

    def get_last_assistant_text(self) -> str | None:
        texts = self.get_recent_assistant_texts()
        return texts[0] if texts else None

    def get_recent_assistant_texts(self) -> tuple[str, ...]:
        return self._inspector.recent_assistant_texts(self.agent.state.messages)


def _latest_compaction_payload(
    entries: Sequence[AgentTranscriptRecord],
) -> dict[str, object] | None:
    for entry in reversed(entries):
        if (
            entry.kind != CONTEXT_COMPACTION_CHECKPOINT_KIND
            or not isinstance(entry.payload, ContextCompactionCheckpoint)
        ):
            continue
        checkpoint = entry.payload
        details = checkpoint.details if isinstance(checkpoint.details, Mapping) else {}
        plan = details.get("compactionPlan")
        return {
            "entryId": entry.record_id,
            "firstKeptEntryId": checkpoint.first_kept_record_id,
            "tokensBefore": checkpoint.tokens_before,
            "fromHook": checkpoint.from_hook,
            "plan": dict(plan) if isinstance(plan, Mapping) else None,
        }
    return None
