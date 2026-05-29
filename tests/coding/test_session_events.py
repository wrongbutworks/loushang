from __future__ import annotations

from typing import get_args

from loushang.agent import AgentEvent


def test_agent_session_event_accepts_core_agent_event() -> None:
    from loushang.coding.event import AgentSessionEvent

    event: AgentSessionEvent = {"type": "agent_start"}
    assert event["type"] == "agent_start"


def test_agent_session_event_accepts_compaction_extension_event() -> None:
    from loushang.coding.event import AgentSessionEvent

    event: AgentSessionEvent = {
        "type": "compaction_start",
        "reason": "manual",
    }
    assert event["type"] == "compaction_start"


def test_agent_session_event_accepts_branch_summary_events() -> None:
    from loushang.coding.event import AgentSessionEvent

    start: AgentSessionEvent = {
        "type": "branch_summary_start",
        "target_id": "t1",
        "old_leaf_id": "l1",
        "summarize": True,
    }
    end: AgentSessionEvent = {
        "type": "branch_summary_end",
        "target_id": "t1",
        "old_leaf_id": "l1",
        "new_leaf_id": "n1",
        "summary_entry_id": "s1",
        "cancelled": False,
        "aborted": False,
    }

    assert start["type"] == "branch_summary_start"
    assert end["type"] == "branch_summary_end"


def test_agent_session_event_accepts_auto_retry_events() -> None:
    from loushang.coding.event import AgentSessionEvent

    start: AgentSessionEvent = {
        "type": "auto_retry_start",
        "attempt": 1,
        "max_attempts": 2,
        "delay_ms": 250,
        "error_message": "503 service unavailable",
    }
    end: AgentSessionEvent = {
        "type": "auto_retry_end",
        "success": False,
        "attempt": 2,
        "final_error": "503 service unavailable",
    }

    assert start["type"] == "auto_retry_start"
    assert end["type"] == "auto_retry_end"


def test_agent_session_event_accepts_queue_update() -> None:
    from loushang.coding.event import AgentSessionEvent

    event: AgentSessionEvent = {
        "type": "queue_update",
        "steering": ["a"],
        "follow_up": ["b"],
    }
    assert event["steering"] == ["a"]


def test_agent_session_event_accepts_session_info_changed() -> None:
    from loushang.coding.event import AgentSessionEvent

    event: AgentSessionEvent = {
        "type": "session_info_changed",
        "name": "Demo",
    }
    assert event["name"] == "Demo"


def test_agent_session_event_extends_base_agent_event_union() -> None:
    from loushang.coding.event import AgentSessionEvent

    assert len(get_args(AgentSessionEvent)) > len(get_args(AgentEvent))


def test_serialize_session_event_uses_pi_json_keys_for_coding_events() -> None:
    from loushang.coding.event import serialize_session_event

    payload = serialize_session_event(
        {
            "type": "queue_update",
            "steering": ["a"],
            "follow_up": ["b"],
        }
    )

    assert payload == {
        "type": "queue_update",
        "steering": ["a"],
        "followUp": ["b"],
    }

    assert serialize_session_event({"type": "session_info_changed", "name": "Demo"}) == {
        "type": "session_info_changed",
        "name": "Demo",
    }


def test_serialize_session_event_uses_pi_json_keys_for_branch_summary_events() -> None:
    from loushang.coding.event import serialize_session_event

    start_payload = serialize_session_event(
        {
            "type": "branch_summary_start",
            "target_id": "t1",
            "old_leaf_id": "l1",
            "summarize": True,
        }
    )
    end_payload = serialize_session_event(
        {
            "type": "branch_summary_end",
            "target_id": "t1",
            "old_leaf_id": "l1",
            "new_leaf_id": "n1",
            "summary_entry_id": "s1",
            "cancelled": False,
            "aborted": False,
            "error_message": "boom",
        }
    )

    assert start_payload == {
        "type": "branch_summary_start",
        "targetId": "t1",
        "oldLeafId": "l1",
        "summarize": True,
    }
    assert end_payload == {
        "type": "branch_summary_end",
        "targetId": "t1",
        "oldLeafId": "l1",
        "newLeafId": "n1",
        "summaryEntryId": "s1",
        "cancelled": False,
        "aborted": False,
        "errorMessage": "boom",
    }


def test_serialize_session_event_uses_pi_json_keys_for_compaction_usage() -> None:
    from loushang.coding.event import serialize_session_event
    from loushang.coding.session.types import ContextUsageSnapshot

    usage = ContextUsageSnapshot(
        tokens=85,
        context_window=100,
        reserve_tokens=10,
        compact_percent=80,
        keep_recent_tokens=32,
        percent_threshold_tokens=80,
        reserve_threshold_tokens=90,
        threshold_tokens=80,
        threshold_reason="compact_percent",
        percent=85.0,
        source="assistant_usage",
        last_usage_index=0,
        stale_after_compaction=False,
        compactable=True,
        reason="threshold",
    )

    start_payload = serialize_session_event(
        {
            "type": "compaction_start",
            "reason": "threshold",
            "usage": usage,
        }
    )
    end_payload = serialize_session_event(
        {
            "type": "compaction_end",
            "reason": "threshold",
            "result": {"ok": True},
            "aborted": False,
            "will_retry": False,
            "usage_before": usage,
            "usage_after": {**usage.__dict__, "tokens": None, "percent": None, "stale_after_compaction": True},
        }
    )

    assert start_payload["usage"]["contextWindow"] == 100
    assert start_payload["usage"]["compactPercent"] == 80
    assert start_payload["usage"]["keepRecentTokens"] == 32
    assert start_payload["usage"]["thresholdReason"] == "compact_percent"
    assert "context_window" not in start_payload["usage"]

    assert end_payload["usageBefore"]["thresholdTokens"] == 80
    assert end_payload["usageAfter"]["tokens"] is None
    assert end_payload["usageAfter"]["staleAfterCompaction"] is True
    assert "usage_before" not in end_payload
    assert "usage_after" not in end_payload


def test_serialize_session_event_uses_pi_json_keys_for_auto_retry_events() -> None:
    from loushang.coding.event import serialize_session_event

    start_payload = serialize_session_event(
        {
            "type": "auto_retry_start",
            "attempt": 1,
            "max_attempts": 3,
            "delay_ms": 250,
            "error_message": "network error",
        }
    )
    end_payload = serialize_session_event(
        {
            "type": "auto_retry_end",
            "success": False,
            "attempt": 2,
            "final_error": "503 service unavailable",
        }
    )

    assert start_payload == {
        "type": "auto_retry_start",
        "attempt": 1,
        "maxAttempts": 3,
        "delayMs": 250,
        "errorMessage": "network error",
    }
    assert end_payload == {
        "type": "auto_retry_end",
        "success": False,
        "attempt": 2,
        "finalError": "503 service unavailable",
    }


def test_serialize_session_event_uses_pi_json_keys_for_package_progress_events() -> None:
    from loushang.coding.event import serialize_session_event

    payload = serialize_session_event(
        {
            "type": "package_progress",
            "progress_type": "start",
            "action": "install",
            "source": "pypi:acme-review-pack==1.2.3",
            "message": "Installing pypi:acme-review-pack==1.2.3...",
            "target_path": "/tmp/packages/python/acme-review-pack",
        }
    )

    assert payload == {
        "type": "package_progress",
        "progressType": "start",
        "action": "install",
        "source": "pypi:acme-review-pack==1.2.3",
        "message": "Installing pypi:acme-review-pack==1.2.3...",
        "targetPath": "/tmp/packages/python/acme-review-pack",
    }


def test_serialize_session_event_uses_pi_json_keys_for_base_agent_events() -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage
    from loushang.coding.event import serialize_session_event

    payload = serialize_session_event(
        {
            "type": "message_update",
            "message": AssistantMessage(
                role="assistant",
                content=[TextPart(type="text", text="hello")],
                api="anthropic-messages",
                provider="anthropic",
                model="claude-sonnet",
                response_id="resp-1",
                usage=Usage(
                    input=1,
                    output=2,
                    cache_read=3,
                    cache_write=4,
                    total_tokens=5,
                    cost={"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0},
                ),
                stop_reason="stop",
                error_message=None,
                timestamp=1.0,
            ),
            "assistant_message_event": {
                "type": "text_delta",
                "content_index": 0,
                "delta": "he",
                "partial": AssistantMessage(
                    role="assistant",
                    content=[TextPart(type="text", text="he")],
                    api="anthropic-messages",
                    provider="anthropic",
                    model="claude-sonnet",
                    response_id="resp-1",
                    usage=Usage(
                        input=1,
                        output=2,
                        cache_read=3,
                        cache_write=4,
                        total_tokens=5,
                        cost={"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0},
                    ),
                    stop_reason="stop",
                    error_message=None,
                    timestamp=1.0,
                ),
            },
        }
    )

    assert payload["assistantMessageEvent"]["contentIndex"] == 0
    assert payload["message"]["responseId"] == "resp-1"
    assert payload["message"]["stopReason"] == "stop"
    assert "assistant_message_event" not in payload


def test_project_session_event_can_attach_rendered_tool_payloads() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.ai.types import TextPart
    from loushang.coding.event import project_session_event
    from loushang.coding.tools import ToolDefinition, ToolRenderRuntime

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[TextPart(type="text", text="ok")], details={})

    def render_call(args, theme, context):
        del theme
        context.state["path"] = args["path"]
        return {"text": f"call {args['path']}"}

    def render_result(result, options, theme, context):
        del theme
        return {
            "text": f"{context.state['path']} {result.content[0].text} partial={options.isPartial} expanded={options.expanded}",
            "className": "tool-row",
        }

    definition = ToolDefinition(
        name="read",
        label="Read",
        description="Read files",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
        render_call=render_call,
        render_result=render_result,
    )
    runtime = ToolRenderRuntime()

    def resolver(name):
        return definition if name == "read" else None

    start_event = {
        "type": "tool_execution_start",
        "tool_call_id": "tc1",
        "tool_name": "read",
        "args": {"path": "README.md"},
    }
    update_event = {
        "type": "tool_execution_update",
        "tool_call_id": "tc1",
        "tool_name": "read",
        "args": {"path": "README.md"},
        "partial_result": AgentToolResult(content=[TextPart(type="text", text="partial")], details={}),
    }
    end_event = {
        "type": "tool_execution_end",
        "tool_call_id": "tc1",
        "tool_name": "read",
        "result": AgentToolResult(
            content=[TextPart(type="text", text="final")],
            details={"fullOutputPath": "/tmp/read-full.txt"},
        ),
        "is_error": False,
    }

    default_payload = project_session_event(start_event, event_view="tools")[0]
    start_payload = project_session_event(
        start_event,
        event_view="tools",
        tool_render_runtime=runtime,
        tool_definition_resolver=resolver,
    )[0]
    update_payload = project_session_event(
        update_event,
        event_view="tools",
        tool_render_runtime=runtime,
        tool_definition_resolver=resolver,
    )[0]
    end_payload = project_session_event(
        end_event,
        event_view="tools",
        tool_render_runtime=runtime,
        tool_definition_resolver=resolver,
        tool_render_expanded=True,
    )[0]

    assert "renderedToolCall" not in default_payload
    assert start_payload["renderedToolCall"] == {
        "type": "text",
        "text": "call README.md",
        "plainText": "call README.md",
        "contractVersion": 1,
        "status": "running",
    }
    assert update_payload["renderedToolResult"] == {
        "type": "text",
        "text": "README.md partial partial=True expanded=False",
        "plainText": "README.md partial partial=True expanded=False",
        "className": "tool-row",
        "isPartial": True,
        "expanded": False,
        "contractVersion": 1,
        "status": "partial",
        "collapsedText": "README.md partial partial=True expanded=False",
        "artifacts": [],
    }
    assert end_payload["renderedToolResult"] == {
        "type": "text",
        "text": "README.md final partial=False expanded=True",
        "plainText": "README.md final partial=False expanded=True",
        "className": "tool-row",
        "isPartial": False,
        "expanded": True,
        "contractVersion": 1,
        "status": "ok",
        "collapsedText": "README.md final partial=False expanded=False",
        "expandedText": "README.md final partial=False expanded=True",
        "artifacts": [{"type": "file", "path": "/tmp/read-full.txt", "name": "read-full.txt"}],
    }


def test_project_session_event_marks_rendered_tool_error_status() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.ai.types import TextPart
    from loushang.coding.event import project_session_event
    from loushang.coding.tools import ToolDefinition, ToolRenderRuntime

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[TextPart(type="text", text="ok")], details={})

    def render_result(result, options, theme, context):
        del options, theme, context
        return {"text": result.content[0].text}

    definition = ToolDefinition(
        name="bash",
        label="Bash",
        description="Run commands",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
        render_result=render_result,
    )

    payload = project_session_event(
        {
            "type": "tool_execution_end",
            "tool_call_id": "tc1",
            "tool_name": "bash",
            "result": AgentToolResult(content=[TextPart(type="text", text="boom")], details={}),
            "is_error": True,
        },
        event_view="tools",
        tool_render_runtime=ToolRenderRuntime(),
        tool_definition_resolver=lambda name: definition if name == "bash" else None,
    )[0]

    assert payload["renderedToolResult"]["status"] == "error"


def test_project_session_event_structures_tool_ui_state_and_bash_artifacts() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.ai.types import TextPart
    from loushang.coding.event import project_session_event
    from loushang.coding.tools import ToolDefinition, ToolRenderRuntime

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[TextPart(type="text", text="ok")], details={})

    def render_result(result, options, theme, context):
        del options, theme, context
        return {"text": result.content[0].text}

    definition = ToolDefinition(
        name="bash",
        label="Bash",
        description="Run commands",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
        render_result=render_result,
    )

    def project(details):
        return project_session_event(
            {
                "type": "tool_execution_end",
                "tool_call_id": "tc1",
                "tool_name": "bash",
                "result": AgentToolResult(content=[TextPart(type="text", text="out")], details=details),
                "is_error": False,
                "duration_ms": 123,
            },
            event_view="tools",
            tool_render_runtime=ToolRenderRuntime(),
            tool_definition_resolver=lambda name: definition if name == "bash" else None,
        )[0]["renderedToolResult"]

    timed_out = project(
        {
            "timed_out": True,
            "stdout_artifact_path": "/tmp/stdout.log",
            "stderr_artifact_path": "/tmp/stderr.log",
        }
    )
    cancelled = project({"cancelled": True, "durationMs": 456})

    assert timed_out["status"] == "timed_out"
    assert timed_out["durationMs"] == 123
    assert timed_out["artifacts"] == [
        {"type": "file", "path": "/tmp/stdout.log", "name": "stdout.log", "stream": "stdout"},
        {"type": "file", "path": "/tmp/stderr.log", "name": "stderr.log", "stream": "stderr"},
    ]
    assert cancelled["status"] == "cancelled"
    assert cancelled["durationMs"] == 456


def test_project_session_event_omits_rendered_tool_payload_when_renderer_fails() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.ai.types import TextPart
    from loushang.coding.event import project_session_event
    from loushang.coding.tools import ToolDefinition, ToolRenderRuntime

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[TextPart(type="text", text="ok")], details={})

    def render_call(args, theme, context):
        del args, theme, context
        raise RuntimeError("renderer failed")

    definition = ToolDefinition(
        name="read",
        label="Read",
        description="Read files",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
        render_call=render_call,
    )

    def resolver(name):
        return definition if name == "read" else None

    payload = project_session_event(
        {
            "type": "tool_execution_start",
            "tool_call_id": "tc1",
            "tool_name": "read",
            "args": {"path": "README.md"},
        },
        event_view="tools",
        tool_render_runtime=ToolRenderRuntime(),
        tool_definition_resolver=resolver,
    )[0]

    assert payload["type"] == "tool_execution_start"
    assert "renderedToolCall" not in payload
