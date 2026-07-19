from __future__ import annotations

import base64
import html
import json
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from loushang.coding.session.introspection import build_session_stats
from loushang.harness.agent_transcript import AgentTranscriptProfile
from loushang.harness.conversation import (
    NativeConversationHeaderCodec,
    NativeConversationRecordCodec,
)
from loushang.protocol import require_json_mapping

from .tool_renderer import render_entry_tree, render_tool_sections, render_transcript

if TYPE_CHECKING:
    from loushang.coding.session.agent_session import AgentSession

_PROFILE = AgentTranscriptProfile.default()
_HEADER_CODEC = NativeConversationHeaderCodec()
_RECORD_CODEC = NativeConversationRecordCodec(_PROFILE.payload_codecs)


def export_session_to_html(
    session: AgentSession, output_path: str | None = None
) -> str:
    stats = build_session_stats(session)
    messages = list(session.get_session_context().messages)
    path = (
        Path(output_path) if output_path is not None else _default_export_path(session)
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    template = _read_asset("template.html")
    css = _read_asset("template.css")
    js = _read_asset("template.js")
    theme = _export_theme(session)
    renderer = _custom_message_renderer(session)
    context_usage = stats.context_usage
    entries = session.session_manager.get_entries()
    branch_entries = session.session_manager.get_branch()
    session_data = _encode_session_data(
        {
            "header": dict(
                _HEADER_CODEC.encode_header(session.session_manager.get_header())
            ),
            "entries": [dict(_RECORD_CODEC.encode_record(entry)) for entry in entries],
            "leafId": session.session_manager.get_leaf_id(),
            "stats": require_json_mapping(
                asdict(stats),
                name="session_export.stats",
            ),
            "tree": {
                "entryCount": len(entries),
                "leafId": session.session_manager.get_leaf_id(),
            },
            "systemPrompt": session.agent.system_prompt,
            "tools": [
                {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                }
                for definition in session.get_all_tools()
            ],
        }
    )
    html_output = (
        template.replace(
            "{{TITLE}}", html.escape(session.session_name or session.session_id)
        )
        .replace("{{STYLE}}", _apply_theme(css, theme))
        .replace("{{SCRIPT}}", js)
        .replace("{{SESSION_ID}}", html.escape(session.session_id))
        .replace("{{SESSION_NAME}}", html.escape(session.session_name or ""))
        .replace("{{ENTRY_COUNT}}", str(stats.entry_count))
        .replace("{{MESSAGE_COUNT}}", str(stats.message_count))
        .replace("{{ACTIVE_TOOL_COUNT}}", str(stats.active_tool_count))
        .replace(
            "{{ESTIMATED_CONTEXT_TOKENS}}",
            str(context_usage.estimated_context_tokens if context_usage else 0),
        )
        .replace(
            "{{SESSION_TREE}}",
            render_entry_tree(entries, leaf_id=session.session_manager.get_leaf_id()),
        )
        .replace(
            "{{TRANSCRIPT}}",
            render_transcript(
                branch_entries,
                custom_renderer=renderer,
                theme=theme,
            ),
        )
        .replace(
            "{{TOOL_SECTIONS}}",
            render_tool_sections(
                messages,
                tool_definition_resolver=session.get_tool_definition,
                theme=theme,
                cwd=session.session_manager.get_cwd(),
            ),
        )
        .replace("{{SESSION_DATA}}", session_data)
    )

    path.write_text(html_output, encoding="utf-8")
    return str(path)


def _read_asset(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def _default_export_path(session: AgentSession) -> Path:
    session_dir = session.session_manager.get_session_dir()
    return session_dir / f"{session.session_id}-export.html"


def _encode_session_data(data: dict[str, object]) -> str:
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(serialized.encode("utf-8")).decode("ascii")


def _custom_message_renderer(session: AgentSession):
    runner = getattr(session, "extension_runner", None)
    getter = (
        getattr(runner, "get_message_renderer", None) if runner is not None else None
    )
    return getter if callable(getter) else None


def _export_theme(session: AgentSession) -> dict[str, str]:
    theme = getattr(session, "export_theme", None)
    if isinstance(theme, dict):
        return {str(key): str(value) for key, value in theme.items()}
    return {}


def _apply_theme(css: str, theme: dict[str, str]) -> str:
    if not theme:
        return css
    variables = "\n".join(
        f"  --{html.escape(key)}: {html.escape(value)};"
        for key, value in sorted(theme.items())
    )
    return ":root {\n" + variables + "\n}\n" + css
