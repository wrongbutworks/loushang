from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import ClassVar

from loushang.harness.tools.workspace.output_preview import (
    DEFAULT_TOOL_OUTPUT_PREVIEW_LINES,
    collapse_tool_output_preview,
    drop_tool_timing_tail_line,
    prefers_tail_tool_output,
)
from loushang.harnesstui.conversation.screen_app import (
    ACTIVE_RENDER_INTERVAL_MS as ACTIVE_RENDER_INTERVAL_MS,
)
from loushang.harnesstui.conversation.screen_frame import ScreenFrameCopy
from loushang.harnesstui.conversation.screen_state import ScreenConversationState
from loushang.harnesstui.conversation.transcript_presentation import (
    ConversationTranscriptCopy,
    ConversationTranscriptPresentationProfile,
    ProfiledScreenConversationApp,
    ScreenConversationPresentationProfile,
)
from loushang.harnesstui.conversation.transcript_style import (
    apply_transcript_style as apply_coding_transcript_style,
)
from loushang.tui import (
    Composer,
    LoushangWelcomePanel,
    loushang_welcome_theme,
)
from loushang.tui.theme import ThemeResolver
from loushang.tui.transcript import (
    DisplayRecord,
    ToolExecutionRecord,
)
from loushang.tui.ui_parts.transcript import DEFAULT_STABLE_TRANSCRIPT_CACHE_ENTRY_LIMIT

DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET = 320
DEFAULT_STABLE_RENDER_CACHE_ENTRY_LIMIT = DEFAULT_STABLE_TRANSCRIPT_CACHE_ENTRY_LIMIT

_CODING_SCREEN_FRAME_COPY = ScreenFrameCopy(
    working_label="Working",
    steer_label="Messages to be submitted after next tool call",
    steer_hint="press esc to interrupt and send immediately",
    followup_label="Queued follow-up inputs",
    followup_hint="alt + ↑ edit last queued message",
)


def _coding_compaction_summary(summary: str) -> str:
    return f"Compacted summary:\n\n{summary.strip()}"


def _terminal_transcript_theme() -> ThemeResolver:
    return ThemeResolver(
        defaults={
            "markdown.heading": {"color": "yellow"},
            "markdown.link": {"color": "blue"},
            "markdown.link.url": {"color": "bright_black"},
            "markdown.code.inline": {"color": "cyan"},
            "markdown.code.block": {"color": "green"},
            "markdown.code.block.border": {"color": "bright_black"},
            "markdown.code.indent": {"text": ""},
            "markdown.quote.text": {"color": "bright_black"},
            "markdown.quote.border": {"color": "bright_black"},
            "markdown.hr": {"color": "bright_black"},
            "markdown.list.bullet": {"color": "green"},
            "transcript.divider": {"color": "bright_black", "dim": True},
            "transcript.error": {"color": "red"},
            "transcript.tool.action": {"color": "bright_cyan"},
            "transcript.tool.connector": {"color": "bright_black", "dim": True},
            "transcript.tool.error_marker": {"color": "red", "bold": True},
            "transcript.tool.flag": {"color": "bright_cyan"},
            "transcript.tool.marker": {"color": "bright_cyan", "bold": True},
            "transcript.tool.meta": {"color": "bright_black", "dim": True},
            "transcript.tool.verb": {"bold": True},
        }
    )


def _screen_coding_display_record(
    record: DisplayRecord, *, cwd: str = ""
) -> DisplayRecord:
    if not isinstance(record, ToolExecutionRecord):
        return record
    name = _compact_display_paths(record.name, cwd=cwd)
    command = "" if _tool_command_duplicates_heading(record) else record.command
    output = drop_tool_timing_tail_line(record.output)
    if record.output_kind == "text":
        output = collapse_tool_output_preview(
            output,
            max_lines=DEFAULT_TOOL_OUTPUT_PREVIEW_LINES,
            tail=prefers_tail_tool_output(name),
        )
    if name == record.name and command == record.command and output == record.output:
        return record
    return replace(record, name=name, command=command, output=output)


def _tool_command_duplicates_heading(record: ToolExecutionRecord) -> bool:
    if not record.command:
        return False
    return _normalize_tool_text(record.command) == _normalize_tool_text(record.name)


def _normalize_tool_text(text: str) -> str:
    return " ".join(text.strip().split())


_ABSOLUTE_PATH_RE = re.compile(r"(?P<prefix>^|[\s\"'=])(?P<path>/[^\s\"']+)")


def _compact_display_paths(text: str, *, cwd: str) -> str:
    home = _normalized_path(os.path.expanduser("~"))
    normalized_cwd = _normalized_path(cwd)

    def replace_path(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        path = match.group("path")
        return prefix + _compact_absolute_path(path, cwd=normalized_cwd, home=home)

    return _ABSOLUTE_PATH_RE.sub(replace_path, text)


def _compact_absolute_path(path: str, *, cwd: str, home: str) -> str:
    if cwd and cwd != "/" and (path == cwd or path.startswith(f"{cwd}/")):
        relative = path[len(cwd) :].lstrip("/")
        return relative or "."
    if home and home != "/" and (path == home or path.startswith(f"{home}/")):
        return "~" + path[len(home) :]
    return path


def _normalized_path(path: str) -> str:
    normalized = path.rstrip("/")
    return normalized or path


def _screen_transcript_record_render_width(record: DisplayRecord, *, width: int) -> int:
    if isinstance(record, ToolExecutionRecord):
        return max(1, width - 2)
    return width


def _cwd_label(cwd: str) -> str:
    if not cwd:
        return "cwd"
    return cwd.rstrip("/").rsplit("/", 1)[-1] or cwd


def _project_coding_display_record(
    record: DisplayRecord,
    *,
    context: str,
) -> DisplayRecord:
    return _screen_coding_display_record(record, cwd=context)


def _coding_welcome_panel(
    state: ScreenConversationState,
    *,
    theme: ThemeResolver | None,
) -> LoushangWelcomePanel:
    return LoushangWelcomePanel(
        directory=state.cwd,
        session=state.session_label or "",
        model=state.model_label or "",
        theme=theme,
    )


_CODING_TRANSCRIPT_PRESENTATION_PROFILE = ConversationTranscriptPresentationProfile[
    str
](
    copy=ConversationTranscriptCopy(
        user_prompt_prefix="› ",
        assistant_prefix="• ",
        error_prefix="■ Error: ",
        context_compaction_prefix="• ",
        tool_success_prefix="• Ran ",
        tool_error_prefix="■ Ran ",
        worked_divider="─",
        tool_command_prefix="  │ ",
        tool_first_output_prefix="  └ ",
        tool_continuation_prefix="    ",
    ),
    project_record=_project_coding_display_record,
    record_render_width=_screen_transcript_record_render_width,
    style_line=apply_coding_transcript_style,
)

_CODING_SCREEN_PRESENTATION_PROFILE = ScreenConversationPresentationProfile[str](
    transcript=_CODING_TRANSCRIPT_PRESENTATION_PROFILE,
    transcript_context=lambda state: state.cwd,
    frame_copy=_CODING_SCREEN_FRAME_COPY,
    welcome_panel=_coding_welcome_panel,
)


@dataclass(slots=True)
class ScreenCodingTuiApp(ProfiledScreenConversationApp):
    """Coding product binding over the shared profiled conversation screen."""

    screen_presentation_profile: ClassVar[
        ScreenConversationPresentationProfile[str]
    ] = _CODING_SCREEN_PRESENTATION_PROFILE
    composer: Composer = field(
        default_factory=lambda: Composer(prompt="› ", continuation_prompt="  ")
    )
    transcript_theme: ThemeResolver = field(default_factory=_terminal_transcript_theme)
    welcome_theme: ThemeResolver | None = field(default_factory=loushang_welcome_theme)
    active_transcript_line_budget: int = DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET
    compaction_summary_formatter: Callable[[str], str] = field(
        default=_coding_compaction_summary,
        repr=False,
    )


__all__ = ["ScreenCodingTuiApp"]
