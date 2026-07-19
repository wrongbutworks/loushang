from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from loushang.agent import Agent
from loushang.ai.model import ModelSelection
from loushang.coding.session.usage_payload import serialize_context_usage_payload
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    AgentTranscriptRecord,
    ContextCompactionCheckpoint,
)
from loushang.harness.session.inspection import (
    AgentSessionInspector,
    AgentSessionState,
    ContextUsage,
    SessionStats,
)


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
    _runtime: AgentSessionInspector = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._runtime = AgentSessionInspector(
            agent=self.agent,
            session=self.session_manager,
            get_session_id=lambda: self.session_manager.get_session_record().session_id,
            get_session_name=lambda: (
                self.session_manager.get_session_record().metadata.name
            ),
            get_active_tool_names=self.get_active_tool_names,
            is_retrying=self.is_retrying,
            is_compacting=self.is_compacting,
            get_last_diagnostics=self.get_last_diagnostics,
            get_model_selection=self.get_model_selection,
            is_host_running=self.is_host_running,
            get_compaction_reserve_tokens=self.get_compaction_reserve_tokens,
            get_compaction_compact_percent=self.get_compaction_compact_percent,
            get_compaction_keep_recent_tokens=self.get_compaction_keep_recent_tokens,
        )

    def get_state(
        self, *, steering: list[str], follow_up: list[str]
    ) -> AgentSessionState:
        return self._runtime.get_state(steering=steering, follow_up=follow_up)

    def get_context_usage(self) -> ContextUsage | None:
        return self._runtime.get_context_usage()

    def build_session_stats(self) -> SessionStats:
        return self._runtime.build_session_stats()

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
        return self._runtime.get_user_messages_for_forking()

    def get_pi_style_user_messages_for_forking(self) -> list[dict[str, str]]:
        return [
            {"entryId": message["entry_id"], "text": message["text"]}
            for message in self.get_user_messages_for_forking()
        ]

    def get_entry_text(self, entry_id: str) -> str | None:
        return self._runtime.get_entry_text(entry_id)

    def get_last_assistant_text(self) -> str | None:
        return self._runtime.get_last_assistant_text()

    def get_recent_assistant_texts(self) -> tuple[str, ...]:
        return self._runtime.get_recent_assistant_texts()


def _latest_compaction_payload(
    entries: Sequence[AgentTranscriptRecord],
) -> dict[str, object] | None:
    for entry in reversed(entries):
        if entry.kind != CONTEXT_COMPACTION_CHECKPOINT_KIND or not isinstance(
            entry.payload, ContextCompactionCheckpoint
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
