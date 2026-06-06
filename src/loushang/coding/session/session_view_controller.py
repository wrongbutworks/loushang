from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from loushang.agent import Agent
from loushang.ai.types import AssistantMessage, ToolCall, ToolResultMessage, UserMessage
from loushang.coding.compaction import estimate_context_tokens
from loushang.coding.message import (
    CompactionEntry,
    CustomMessageEntry,
    SessionMessageEntry,
)
from loushang.coding.session.context_usage import build_context_usage_snapshot
from loushang.coding.session.types import (
    AgentSessionState,
    ContextUsage,
    ModelSelection,
    RunState,
    SessionStats,
)
from loushang.coding.session.usage_payload import serialize_context_usage_payload
from loushang.coding.store import SessionManager


@dataclass
class SessionViewController:
    agent: Agent
    session_manager: SessionManager
    get_active_tool_names: Callable[[], list[str]]
    is_retrying: Callable[[], bool]
    is_compacting: Callable[[], bool]
    get_last_diagnostics: Callable[[int], list[object]]
    get_model_selection: Callable[[], ModelSelection | None]
    get_compaction_reserve_tokens: Callable[[], int] = lambda: 0
    get_compaction_compact_percent: Callable[[], float] = lambda: 100.0
    get_compaction_keep_recent_tokens: Callable[[], int | None] = lambda: None

    def get_state(self, *, steering: list[str], follow_up: list[str]) -> AgentSessionState:
        return AgentSessionState(
            run=RunState(status="running" if self.agent.state.is_streaming else "idle"),
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
        entries = self.session_manager.get_entries()
        branch_entries = self.session_manager.get_branch()

        assistant_message_count = 0
        user_message_count = 0
        tool_call_count = 0
        tool_result_count = 0

        for message in messages:
            if isinstance(message, AssistantMessage):
                assistant_message_count += 1
                tool_call_count += sum(1 for block in message.content if isinstance(block, ToolCall))
            elif isinstance(message, UserMessage):
                user_message_count += 1
            elif isinstance(message, ToolResultMessage):
                tool_result_count += 1

        estimated_context_tokens = estimate_context_tokens(messages).tokens if messages else 0
        snapshot = build_context_usage_snapshot(
            messages,
            branch_entries,
            self.agent.model,
            reserve_tokens=self.get_compaction_reserve_tokens(),
            compact_percent=self.get_compaction_compact_percent(),
            keep_recent_tokens=self.get_compaction_keep_recent_tokens(),
        )
        return ContextUsage(
            message_count=len(messages),
            assistant_message_count=assistant_message_count,
            user_message_count=user_message_count,
            tool_call_count=tool_call_count,
            tool_result_count=tool_result_count,
            custom_message_count=sum(1 for entry in entries if isinstance(entry, CustomMessageEntry)),
            estimated_context_tokens=estimated_context_tokens,
            has_compaction=any(isinstance(entry, CompactionEntry) for entry in entries),
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
        return SessionStats(
            session_id=record.session_id,
            session_name=record.metadata.name,
            entry_count=len(entries),
            message_count=context_usage.message_count if context_usage is not None else 0,
            custom_message_count=sum(1 for entry in entries if isinstance(entry, CustomMessageEntry)),
            active_tool_count=len(self.get_active_tool_names()),
            is_retrying=self.is_retrying(),
            is_compacting=self.is_compacting(),
            has_diagnostics=bool(self.get_last_diagnostics(1)),
            branch_count=_count_leaf_branches(self.session_manager.get_tree()),
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
                    tool_calls += sum(1 for block in content if getattr(block, "type", None) == "toolCall")
                usage = getattr(message, "usage", None)
                if usage is not None:
                    total_input += int(getattr(usage, "input", 0) or 0)
                    total_output += int(getattr(usage, "output", 0) or 0)
                    total_cache_read += int(getattr(usage, "cache_read", 0) or 0)
                    total_cache_write += int(getattr(usage, "cache_write", 0) or 0)
                    cost = getattr(usage, "cost", {})
                    if isinstance(cost, dict):
                        total_cost += float(cost.get("total", sum(value for value in cost.values() if isinstance(value, int | float))))
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
                "total": total_input + total_output + total_cache_read + total_cache_write,
            },
            "cost": total_cost,
            "contextUsage": serialize_context_usage_payload(self.get_context_usage()),
            "latestCompaction": _latest_compaction_payload(self.session_manager.get_branch()),
        }

    def get_user_messages_for_forking(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for entry in self.session_manager.get_entries():
            if not isinstance(entry, SessionMessageEntry):
                continue
            if not isinstance(entry.message, UserMessage):
                continue
            text = _extract_user_message_text(entry.message)
            if not text:
                continue
            messages.append({"entry_id": entry.id, "text": text})
        return messages

    def get_pi_style_user_messages_for_forking(self) -> list[dict[str, str]]:
        return [
            {"entryId": message["entry_id"], "text": message["text"]}
            for message in self.get_user_messages_for_forking()
        ]

    def get_entry_text(self, entry_id: str) -> str | None:
        entry = self.session_manager.get_entry(entry_id)
        if entry is None:
            return None
        if isinstance(entry, SessionMessageEntry) and isinstance(entry.message, UserMessage):
            return _extract_user_message_text(entry.message) or None
        message = getattr(entry, "message", None)
        if isinstance(message, UserMessage):
            return _extract_user_message_text(message) or None
        content = getattr(entry, "content", None)
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            text = "".join(block.text for block in content if getattr(block, "type", None) == "text")
            return text or None
        return None

    def get_last_assistant_text(self) -> str | None:
        texts = self.get_recent_assistant_texts()
        return texts[0] if texts else None

    def get_recent_assistant_texts(self) -> tuple[str, ...]:
        texts: list[str] = []
        for message in reversed(self.agent.state.messages):
            if not isinstance(message, AssistantMessage):
                continue
            text = _extract_assistant_message_text(message)
            if text is not None:
                texts.append(text)
        return tuple(texts)


def _count_leaf_branches(nodes: list[object]) -> int:
    if not nodes:
        return 0

    def _count(node: object) -> int:
        children = getattr(node, "children", [])
        if not children:
            return 1
        return sum(_count(child) for child in children)

    return sum(_count(node) for node in nodes)


def _extract_assistant_message_text(message: AssistantMessage) -> str | None:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content if content.strip() else None
    if isinstance(content, list):
        text = "".join(block.text for block in content if getattr(block, "type", None) == "text")
        return text if text.strip() else None
    return None


def _latest_compaction_payload(entries: list[object]) -> dict[str, object] | None:
    for entry in reversed(entries):
        if not isinstance(entry, CompactionEntry):
            continue
        details = entry.details if isinstance(entry.details, Mapping) else {}
        plan = details.get("compactionPlan")
        return {
            "entryId": entry.id,
            "firstKeptEntryId": entry.first_kept_entry_id,
            "tokensBefore": entry.tokens_before,
            "fromHook": entry.from_hook,
            "plan": dict(plan) if isinstance(plan, Mapping) else None,
        }
    return None


def _extract_user_message_text(message: UserMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")
