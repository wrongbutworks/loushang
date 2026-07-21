"""Coding-specific projections over Harness session inspection values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from loushang.agent import Agent
from loushang.coding.session_manager import SessionManager
from loushang.harness.agent_transcript import (
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    AgentTranscriptRecord,
    ContextCompactionCheckpoint,
)
from loushang.harness.context import serialize_context_usage_payload
from loushang.harness.session import AgentSessionInspector, ContextUsage


def project_pi_session_stats(
    *,
    agent: Agent,
    session_manager: SessionManager,
    context_usage: ContextUsage | None,
) -> dict[str, object]:
    """Project common inspection facts into Coding's Pi-compatible payload."""

    user_messages = 0
    assistant_messages = 0
    tool_results = 0
    tool_calls = 0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    total_cost = 0.0
    messages = list(agent.state.messages)
    for message in messages:
        role = getattr(message, "role", None)
        if role == "user":
            user_messages += 1
        elif role == "assistant":
            assistant_messages += 1
            content = getattr(message, "content", [])
            if isinstance(content, list):
                tool_calls += sum(
                    1 for block in content if getattr(block, "type", None) == "toolCall"
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
    session_file = session_manager.get_session_file()
    return {
        "sessionFile": str(session_file) if session_file is not None else None,
        "sessionId": session_manager.get_session_record().session_id,
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
        "contextUsage": serialize_context_usage_payload(context_usage),
        "latestCompaction": _latest_compaction_payload(session_manager.get_branch()),
    }


def project_pi_fork_candidates(
    inspector: AgentSessionInspector,
) -> list[dict[str, str]]:
    """Project common transcript fork candidates into Coding's wire shape."""

    return [
        {"entryId": message["entry_id"], "text": message["text"]}
        for message in inspector.get_user_messages_for_forking()
    ]


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


__all__ = ["project_pi_fork_candidates", "project_pi_session_stats"]
