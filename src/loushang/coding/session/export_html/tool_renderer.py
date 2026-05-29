from __future__ import annotations

import hashlib
import html
import json
import re

from loushang.agent.types import AgentToolResult
from loushang.ai.types import AssistantMessage, TextPart, ToolCall, ToolResultMessage, UserMessage
from loushang.coding.message import LabelEntry, SessionEntry
from loushang.coding.message.custom_messages import BranchSummaryMessage, CompactionSummaryMessage, CustomMessage
from loushang.coding.tools.presentation import render_tool_result_text
from loushang.coding.tools.rendering import ToolDefinitionResolver, ToolRenderRuntime

from .ansi import render_ansi_pre
from .markdown import render_markdown


def render_transcript(messages: list[object], *, custom_renderer=None, theme: dict[str, str] | None = None) -> str:
    items: list[str] = []
    for index, message in enumerate(messages, start=1):
        items.append(_render_message(message, custom_renderer=custom_renderer, theme=theme or {}, message_id=f"message-{index}"))
    return "\n".join(items)


def render_tool_sections(
    messages: list[object],
    *,
    tool_definition_resolver: ToolDefinitionResolver | None = None,
    theme: dict[str, str] | None = None,
    cwd: str = "",
) -> str:
    calls: list[str] = []
    results: list[str] = []
    theme = theme or {}
    render_runtime = ToolRenderRuntime(cwd=cwd, theme=theme, show_images=False)

    for message in messages:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolCall):
                    rendered = _render_tool_call_with_renderer(
                        render_runtime,
                        tool_definition_resolver,
                        block,
                    )
                    body = (
                        rendered
                        if rendered is not None
                        else (
                            "<strong>"
                            + html.escape(block.name)
                            + "</strong><pre>"
                            + html.escape(json.dumps(block.arguments, indent=2, sort_keys=True))
                            + "</pre>"
                        )
                    )
                    calls.append(_tool_list_item("tool-call-item", block.name, body))
        elif isinstance(message, ToolResultMessage):
            result_flags = []
            if getattr(message, "is_error", False):
                result_flags.append("error")
            if getattr(message, "terminate", False):
                result_flags.append("terminate")
            rendered = _render_tool_result_with_renderer(
                render_runtime,
                tool_definition_resolver,
                message,
            )
            if rendered is None:
                text = render_tool_result_text(message.content, message.details, preserve_ansi=True)
                rendered = (
                    "<strong>"
                    + html.escape(message.tool_name)
                    + "</strong>"
                    + (
                        " <span class=\"tool-status\">" + html.escape(", ".join(result_flags)) + "</span>"
                        if result_flags
                        else ""
                    )
                    + render_ansi_pre(text)
                )
            results.append(
                '<li class="tool-result-item" data-tool-name="'
                + html.escape(message.tool_name)
                + '" data-tool-status="'
                + html.escape(",".join(result_flags) or "ok")
                + '">'
                + rendered
                + "</li>"
            )

    return (
        '<section><h2 id="tool-calls">Tool Calls</h2><ul>'
        + ("".join(calls) or "<li>None</li>")
        + "</ul></section>"
        + '<section><h2 id="tool-results">Tool Results</h2><ul>'
        + ("".join(results) or "<li>None</li>")
        + "</ul></section>"
    )


def _tool_list_item(css_class: str, tool_name: str, body: str) -> str:
    return (
        f'<li class="{html.escape(css_class)}" data-tool-name="{html.escape(tool_name)}">'
        + body
        + "</li>"
    )


def _render_tool_call_with_renderer(
    render_runtime: ToolRenderRuntime,
    resolver: ToolDefinitionResolver | None,
    block: ToolCall,
) -> str | None:
    if resolver is None:
        return None
    try:
        return _render_tool_renderer_output(
            render_runtime.render_event(
                {
                    "type": "tool_execution_start",
                    "tool_call_id": block.id,
                    "tool_name": block.name,
                    "args": block.arguments,
                },
                resolver,
            )
        )
    except Exception:
        return None


def _render_tool_result_with_renderer(
    render_runtime: ToolRenderRuntime,
    resolver: ToolDefinitionResolver | None,
    message: ToolResultMessage,
) -> str | None:
    if resolver is None:
        return None
    result = AgentToolResult(
        content=message.content,
        details=message.details,
        terminate=getattr(message, "terminate", False),
    )
    try:
        event = {
            "type": "tool_execution_end",
            "tool_call_id": message.tool_call_id,
            "tool_name": message.tool_name,
            "result": result,
            "is_error": bool(getattr(message, "is_error", False)),
        }
        collapsed = _render_tool_renderer_output(
            render_runtime.render_event(
                event,
                resolver,
                expanded=False,
            )
        )
        expanded = _render_tool_renderer_output(
            render_runtime.render_event(
                event,
                resolver,
                expanded=True,
            )
        )
        status = _rendered_tool_result_status(message)
        if collapsed is None and expanded is None:
            return None
        if expanded is None or expanded == collapsed:
            return _rendered_result_container(collapsed or "", expanded=False, status=status)
        if collapsed is None:
            return _rendered_result_container(expanded, expanded=True, status=status)
        return (
            _rendered_result_container(collapsed, expanded=False, status=status)
            + _rendered_result_container(expanded, expanded=True, status=status)
        )
    except Exception:
        return None


def _render_tool_renderer_output(rendered: object) -> str | None:
    if rendered is None:
        return None
    if isinstance(rendered, str):
        return render_ansi_pre(rendered)
    if isinstance(rendered, dict):
        html_output = rendered.get("html")
        if isinstance(html_output, str):
            return html_output
        text = rendered.get("text")
        if isinstance(text, str):
            return render_ansi_pre(text)
    return None


def _rendered_result_container(rendered: str, *, expanded: bool, status: str) -> str:
    return (
        '<div class="tool-rendered-result'
        + (" expanded" if expanded else "")
        + '" data-render-contract-version="1" data-render-status="'
        + html.escape(status)
        + '" data-expanded="'
        + ("true" if expanded else "false")
        + '">'
        + rendered
        + "</div>"
    )


def _rendered_tool_result_status(message: ToolResultMessage) -> str:
    if getattr(message, "is_error", False):
        return "error"
    if getattr(message, "terminate", False):
        return "terminate"
    return "ok"


def render_entry_tree(entries: list[SessionEntry], *, leaf_id: str | None) -> str:
    if not entries:
        return "<p>No entries</p>"
    label_by_target = {
        entry.target_id: entry.label
        for entry in entries
        if isinstance(entry, LabelEntry) and entry.label is not None
    }
    rows = []
    for entry in entries:
        label = label_by_target.get(entry.id)
        label_html = f' <span class="entry-label">{html.escape(label)}</span>' if label else ""
        active = " active" if entry.id == leaf_id else ""
        rows.append(
            f'<li id="entry-{html.escape(entry.id)}" class="tree-entry{active}">'
            f'<a href="#entry-{html.escape(entry.id)}">'
            f'<code>{html.escape(entry.type)}</code> '
            f'<span class="entry-id">{html.escape(entry.id)}</span>'
            "</a>"
            f"{label_html}"
            "</li>"
        )
    return "<ul>" + "".join(rows) + "</ul>"


def _render_message(message: object, *, custom_renderer=None, theme: dict[str, str], message_id: str | None = None) -> str:
    if isinstance(message, UserMessage):
        body = message.content if isinstance(message.content, str) else "\n".join(
            block.text for block in message.content if isinstance(block, TextPart)
        )
        return _wrap("user", "User", body, message_id=message_id)

    if isinstance(message, AssistantMessage):
        parts: list[str] = []
        for block in message.content:
            if isinstance(block, TextPart):
                parts.append(block.text)
            elif isinstance(block, ToolCall):
                parts.append(f"[tool call] {block.name} {json.dumps(block.arguments, sort_keys=True)}")
        return _wrap("assistant", "Assistant", "\n".join(parts), message_id=message_id)

    if isinstance(message, ToolResultMessage):
        body = render_tool_result_text(message.content, message.details, preserve_ansi=True)
        return _wrap("tool-result", f"Tool Result: {message.tool_name}", body, message_id=message_id, body_format="ansi")

    if isinstance(message, BranchSummaryMessage):
        return _wrap("branch-summary", "Branch Summary", message.summary, message_id=message_id)

    if isinstance(message, CompactionSummaryMessage):
        return _wrap("compaction-summary", f"Compaction Summary: {message.tokens_before} tokens", message.summary, message_id=message_id)

    if isinstance(message, CustomMessage):
        rendered = _render_custom_message_with_renderer(message, custom_renderer=custom_renderer, theme=theme, message_id=message_id)
        if rendered is not None:
            return rendered
        body = message.content if isinstance(message.content, str) else "\n".join(
            block.text for block in message.content if isinstance(block, TextPart)
        )
        return _wrap("custom", f"Custom: {message.custom_type}", body, message_id=message_id)

    return _wrap("unknown", "Unknown", repr(message), message_id=message_id)


def _render_custom_message_with_renderer(
    message: CustomMessage,
    *,
    custom_renderer,
    theme: dict[str, str],
    message_id: str | None,
) -> str | None:
    if not callable(custom_renderer):
        return None
    renderer = custom_renderer(message.custom_type)
    if renderer is None:
        return None
    try:
        rendered = renderer(message, {"format": "html_export"}, theme)
    except Exception as exc:
        return _wrap("custom-render-error", f"Custom Renderer Error: {message.custom_type}", str(exc), message_id=message_id)
    if isinstance(rendered, str):
        return _wrap_html("custom rendered", rendered, message.custom_type, message_id=message_id)
    if isinstance(rendered, dict):
        html_output = rendered.get("html")
        if isinstance(html_output, str):
            css_class = rendered.get("className", rendered.get("class_name", "custom rendered"))
            return _wrap_html(str(css_class), html_output, message.custom_type, message_id=message_id)
        text = rendered.get("text")
        title = rendered.get("title", f"Custom: {message.custom_type}")
        css_class = rendered.get("className", rendered.get("class_name", "custom rendered"))
        if isinstance(text, str):
            return _wrap(str(css_class), str(title), text, message_id=message_id)
    return None


def _wrap(
    css_class: str,
    title: str,
    body: str,
    *,
    message_id: str | None = None,
    body_format: str = "markdown",
) -> str:
    search_text = " ".join((title, _searchable_body_text(body))).lower()
    resolved_message_id = message_id or _stable_message_id(css_class, title, body)
    body_html = render_ansi_pre(body) if body_format == "ansi" else render_markdown(body)
    return (
        f'<article id="{html.escape(resolved_message_id)}" class="message {css_class}" data-message-type="{html.escape(css_class)}" '
        f'data-search="{html.escape(search_text)}">'
        f"<h3>{html.escape(title)}</h3>"
        f"{body_html}"
        "</article>"
    )


def _wrap_html(css_class: str, body_html: str, custom_type: str, *, message_id: str | None = None) -> str:
    search_text = html.escape(custom_type.lower())
    resolved_message_id = message_id or _stable_message_id(css_class, custom_type, body_html)
    return (
        f'<article id="{html.escape(resolved_message_id)}" class="message {html.escape(css_class)}" data-message-type="custom" '
        f'data-search="{search_text}">'
        + body_html
        + "</article>"
    )


def _stable_message_id(css_class: str, title: str, body: str) -> str:
    digest = hashlib.sha1(f"{css_class}\0{title}\0{body}".encode("utf-8")).hexdigest()[:12]
    return f"message-{digest}"


def _searchable_body_text(body: str) -> str:
    return re.sub(r"```[A-Za-z0-9_+.#-]*[^\n]*\n(.*?)```", r"\1", body, flags=re.DOTALL)
