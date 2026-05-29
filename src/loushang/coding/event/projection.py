from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Sequence

from loushang.agent.types import AgentToolResult
from loushang.coding.event.serialization import serialize_session_event
from loushang.coding.event.types import AgentSessionEvent
from loushang.coding.message.json_codec import serialize_agent_message, serialize_assistant_message_event
from loushang.coding.message.json_codec import serialize_json_value
from loushang.coding.tools import ToolDefinitionResolver, ToolRenderOutput, ToolRenderRuntime
from loushang.coding.tools.protocol import project_tool_details_for_protocol

JsonEventView = Literal["full", "compact", "assistant_stream", "tools", "final"]

SUPPORTED_JSON_EVENT_VIEWS: tuple[JsonEventView, ...] = ("full", "compact", "assistant_stream", "tools", "final")

_EVENT_SELECTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "assistant": ("assistant_*",),
    "assistant.*": ("assistant_*",),
    "assistant.delta": ("assistant_delta",),
    "assistant.final": ("assistant_final",),
    "final": ("assistant_final",),
    "tool.lifecycle": ("tool_execution_start", "tool_execution_end"),
    "tools": ("tool_execution_*",),
}


def select_events(*patterns: str) -> tuple[str, ...]:
    return patterns


def normalize_event_select(event_select: str | Sequence[str] | None) -> tuple[str, ...]:
    if event_select is None:
        return ()
    if isinstance(event_select, str):
        event_select = (event_select,)
    normalized: list[str] = []
    for pattern in event_select:
        if not isinstance(pattern, str):
            raise TypeError("event_select patterns must be strings")
        if not pattern:
            raise ValueError("event_select patterns must be non-empty")
        normalized.append(pattern)
    return tuple(normalized)


def project_session_event(
    event: AgentSessionEvent,
    *,
    event_view: JsonEventView,
    tool_render_runtime: ToolRenderRuntime | None = None,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    tool_render_expanded: bool = False,
) -> list[dict[str, Any]]:
    if event_view == "full":
        payloads = [serialize_session_event(event)]
        return _with_rendered_tool_payloads(
            payloads,
            event,
            tool_render_runtime=tool_render_runtime,
            tool_definition_resolver=tool_definition_resolver,
            tool_render_expanded=tool_render_expanded,
        )
    if event_view == "compact":
        payloads = _project_compact_event(event)
        return _with_rendered_tool_payloads(
            payloads,
            event,
            tool_render_runtime=tool_render_runtime,
            tool_definition_resolver=tool_definition_resolver,
            tool_render_expanded=tool_render_expanded,
        )
    if event_view == "assistant_stream":
        return _project_assistant_stream_event(event)
    if event_view == "tools":
        payloads = _project_tools_event(event)
        return _with_rendered_tool_payloads(
            payloads,
            event,
            tool_render_runtime=tool_render_runtime,
            tool_definition_resolver=tool_definition_resolver,
            tool_render_expanded=tool_render_expanded,
        )
    if event_view == "final":
        return _project_final_event(event)
    raise ValueError(f"unsupported json event view: {event_view}")


def should_emit_projected_event(payload: dict[str, Any], event_select: Sequence[str]) -> bool:
    if not event_select:
        return True
    event_type = payload.get("type")
    if not isinstance(event_type, str):
        return False
    expanded = _expand_patterns(event_select)
    for pattern in expanded:
        if pattern == "*":
            return True
        if pattern.endswith("*") and event_type.startswith(pattern[:-1]):
            return True
        if event_type == pattern:
            return True
    return False


def shape_stream_event(payload: dict[str, Any], *, event_view: JsonEventView) -> dict[str, Any]:
    shaped = dict(payload)
    event_type = shaped.get("type")
    if isinstance(event_type, str):
        shaped.setdefault("eventType", event_type)
    correlation_id = _event_correlation_id(shaped)
    stream: dict[str, Any] = {
        "kind": "session_event",
        "view": event_view,
    }
    if correlation_id is not None:
        shaped["correlationId"] = correlation_id
        stream["correlationId"] = correlation_id
    shaped["stream"] = stream
    return shaped


def _expand_patterns(patterns: Sequence[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for pattern in patterns:
        aliases = _EVENT_SELECTOR_ALIASES.get(pattern)
        if aliases is not None:
            expanded.extend(aliases)
            continue
        if "." in pattern:
            expanded.append(pattern.replace(".", "_"))
            continue
        expanded.append(pattern)
    return tuple(expanded)


def _project_compact_event(event: AgentSessionEvent) -> list[dict[str, Any]]:
    event_type = event["type"]
    if event_type in {"tool_execution_start", "tool_execution_end"}:
        return [serialize_session_event(event)]
    if event_type == "message_update":
        assistant_delta = _serialize_assistant_delta(event)
        return [assistant_delta] if assistant_delta is not None else []
    if event_type == "message_end":
        assistant_final = _serialize_assistant_final(event)
        return [assistant_final] if assistant_final is not None else []
    return []


def _project_assistant_stream_event(event: AgentSessionEvent) -> list[dict[str, Any]]:
    event_type = event["type"]
    if event_type == "message_update":
        assistant_delta = _serialize_assistant_delta(event)
        return [assistant_delta] if assistant_delta is not None else []
    if event_type == "message_end":
        assistant_final = _serialize_assistant_final(event)
        return [assistant_final] if assistant_final is not None else []
    return []


def _project_tools_event(event: AgentSessionEvent) -> list[dict[str, Any]]:
    if event["type"] in {"tool_execution_start", "tool_execution_update", "tool_execution_end"}:
        return [serialize_session_event(event)]
    return []


def _with_rendered_tool_payloads(
    payloads: list[dict[str, Any]],
    event: AgentSessionEvent,
    *,
    tool_render_runtime: ToolRenderRuntime | None,
    tool_definition_resolver: ToolDefinitionResolver | None,
    tool_render_expanded: bool,
) -> list[dict[str, Any]]:
    if not payloads or tool_render_runtime is None or tool_definition_resolver is None:
        return payloads
    event_type = event["type"]
    if event_type not in {"tool_execution_start", "tool_execution_update", "tool_execution_end"}:
        return payloads
    if event_type == "tool_execution_end":
        collapsed = _serialize_tool_render_output(
            _render_tool_event(
                event,
                tool_render_runtime=tool_render_runtime,
                tool_definition_resolver=tool_definition_resolver,
                expanded=False,
            )
        )
        expanded = _serialize_tool_render_output(
            _render_tool_event(
                event,
                tool_render_runtime=tool_render_runtime,
                tool_definition_resolver=tool_definition_resolver,
                expanded=True,
            )
        )
        serialized = expanded if tool_render_expanded else collapsed
        collapsed_text = _payload_plain_text(collapsed)
        expanded_text = _payload_plain_text(expanded)
    else:
        serialized = _serialize_tool_render_output(
            _render_tool_event(
                event,
                tool_render_runtime=tool_render_runtime,
                tool_definition_resolver=tool_definition_resolver,
                expanded=tool_render_expanded,
            )
        )
        collapsed_text = _payload_plain_text(serialized) if not tool_render_expanded else None
        expanded_text = _payload_plain_text(serialized) if tool_render_expanded else None
    if serialized is None:
        return payloads
    output_key = "renderedToolCall" if event_type == "tool_execution_start" else "renderedToolResult"
    enriched: list[dict[str, Any]] = []
    for payload in payloads:
        updated = dict(payload)
        rendered_payload = _with_render_contract(
            serialized,
            event,
            output_key=output_key,
            expanded=tool_render_expanded,
            collapsed_text=collapsed_text,
            expanded_text=expanded_text,
        )
        if output_key == "renderedToolResult":
            rendered_payload.setdefault("isPartial", event_type == "tool_execution_update")
            rendered_payload.setdefault("expanded", tool_render_expanded)
        updated[output_key] = rendered_payload
        enriched.append(updated)
    return enriched


def _render_tool_event(
    event: AgentSessionEvent,
    *,
    tool_render_runtime: ToolRenderRuntime,
    tool_definition_resolver: ToolDefinitionResolver,
    expanded: bool,
) -> ToolRenderOutput:
    try:
        return tool_render_runtime.render_event(
            event,
            tool_definition_resolver,
            expanded=expanded,
        )
    except Exception:
        return None


def _serialize_tool_render_output(rendered: ToolRenderOutput) -> dict[str, Any] | None:
    if rendered is None:
        return None
    if isinstance(rendered, str):
        return {"type": "text", "text": rendered, "plainText": rendered}
    if isinstance(rendered, dict):
        payload = serialize_json_value(rendered)
        if not isinstance(payload, dict):
            return None
        if isinstance(payload.get("html"), str):
            payload.setdefault("type", "html")
        elif isinstance(payload.get("text"), str):
            payload.setdefault("type", "text")
        else:
            payload.setdefault("type", "custom")
        text = payload.get("text")
        if isinstance(text, str):
            payload.setdefault("plainText", text)
        return payload
    return None


def _with_render_contract(
    payload: dict[str, Any],
    event: AgentSessionEvent,
    *,
    output_key: str,
    expanded: bool,
    collapsed_text: str | None,
    expanded_text: str | None,
) -> dict[str, Any]:
    rendered_payload = dict(payload)
    rendered_payload.setdefault("contractVersion", 1)
    if output_key == "renderedToolCall":
        rendered_payload.setdefault("status", "running")
        return rendered_payload

    rendered_payload.setdefault("status", _rendered_tool_result_status(event))
    duration_ms = _rendered_tool_duration_ms(event, rendered_payload)
    if duration_ms is not None:
        rendered_payload.setdefault("durationMs", duration_ms)
    if collapsed_text is not None:
        rendered_payload.setdefault("collapsedText", collapsed_text)
    if expanded_text is not None:
        rendered_payload.setdefault("expandedText", expanded_text)
    rendered_payload.setdefault("artifacts", _rendered_tool_artifacts(event))
    rendered_payload.setdefault("expanded", expanded)
    return rendered_payload


def _payload_plain_text(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    plain_text = payload.get("plainText")
    if isinstance(plain_text, str):
        return plain_text
    text = payload.get("text")
    return text if isinstance(text, str) else None


def _rendered_tool_result_status(event: AgentSessionEvent) -> str:
    if event["type"] == "tool_execution_update":
        return "partial"
    result = event.get("result")
    if isinstance(result, AgentToolResult) and isinstance(result.details, Mapping):
        if result.details.get("timed_out") is True or result.details.get("timedOut") is True:
            return "timed_out"
        if result.details.get("cancelled") is True or result.details.get("canceled") is True:
            return "cancelled"
    if bool(event.get("is_error", False)):
        return "error"
    if isinstance(result, AgentToolResult) and result.terminate:
        return "terminate"
    return "ok"


def _rendered_tool_duration_ms(event: AgentSessionEvent, payload: Mapping[str, Any]) -> int | None:
    for candidate in (payload.get("durationMs"),):
        resolved = _non_negative_int(candidate)
        if resolved is not None:
            return resolved
    result = event.get("partial_result") if event["type"] == "tool_execution_update" else event.get("result")
    if isinstance(result, AgentToolResult) and isinstance(result.details, Mapping):
        for key in ("durationMs", "duration_ms", "elapsedMs", "elapsed_ms"):
            resolved = _non_negative_int(result.details.get(key))
            if resolved is not None:
                return resolved
    for candidate in (event.get("duration_ms"), event.get("durationMs")):
        resolved = _non_negative_int(candidate)
        if resolved is not None:
            return resolved
    return None


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value >= 0:
        return round(value)
    return None


def _rendered_tool_artifacts(event: AgentSessionEvent) -> list[dict[str, str]]:
    result = event.get("partial_result") if event["type"] == "tool_execution_update" else event.get("result")
    if not isinstance(result, AgentToolResult) or not isinstance(result.details, Mapping):
        return []
    details = project_tool_details_for_protocol(result.details)
    artifacts: list[dict[str, str]] = []
    for key in ("stdout_artifact_path", "stderr_artifact_path", "fullOutputPath"):
        value = details.get(key)
        if isinstance(value, str) and value and all(artifact["path"] != value for artifact in artifacts):
            artifact = {
                "type": "file",
                "path": value,
                "name": _artifact_name(value),
            }
            stream = _artifact_stream(key)
            if stream is not None:
                artifact["stream"] = stream
            artifacts.append(artifact)
    return artifacts


def _artifact_name(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1] or path


def _artifact_stream(key: str) -> str | None:
    if key.startswith("stdout"):
        return "stdout"
    if key.startswith("stderr"):
        return "stderr"
    return None


def _project_final_event(event: AgentSessionEvent) -> list[dict[str, Any]]:
    if event["type"] != "message_end":
        return []
    assistant_final = _serialize_assistant_final(event)
    return [assistant_final] if assistant_final is not None else []


def _serialize_assistant_delta(event: AgentSessionEvent) -> dict[str, Any] | None:
    if event["type"] != "message_update":
        return None
    message = event["message"]
    if getattr(message, "role", None) != "assistant":
        return None
    assistant_event = serialize_assistant_message_event(event["assistant_message_event"])
    assistant_event_type = assistant_event["type"]
    if assistant_event_type in {"text_delta", "thinking_delta", "toolcall_delta"}:
        return {
            "type": "assistant_delta",
            "eventType": assistant_event_type,
            "contentIndex": assistant_event["contentIndex"],
            "delta": assistant_event["delta"],
        }
    return {
        "type": "assistant_event",
        "assistantMessageEvent": assistant_event,
    }


def _serialize_assistant_final(event: AgentSessionEvent) -> dict[str, Any] | None:
    if event["type"] != "message_end":
        return None
    message = event["message"]
    if getattr(message, "role", None) != "assistant":
        return None
    return {
        "type": "assistant_final",
        "message": serialize_agent_message(message),
    }


def _event_correlation_id(payload: dict[str, Any]) -> str | None:
    for key in ("toolCallId", "messageId", "entryId", "sessionId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    message = payload.get("message")
    if isinstance(message, dict):
        value = message.get("id")
        if isinstance(value, str) and value:
            return value
    return None
