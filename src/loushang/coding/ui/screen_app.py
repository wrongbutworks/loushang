from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from loushang.coding.ui.screen_state import ScreenCodingTuiState, ScreenTranscriptWindow
from loushang.coding.ui.transcript_source import ActiveWindowTranscriptSource
from loushang.coding.ui.transcript_style import apply_coding_transcript_style
from loushang.harness.tools.workspace.output_preview import (
    DEFAULT_TOOL_OUTPUT_PREVIEW_LINES,
    collapse_tool_output_preview,
    drop_tool_timing_tail_line,
    prefers_tail_tool_output,
)
from loushang.harnesstui.conversation.reader import TranscriptReaderSurface
from loushang.harnesstui.conversation.source import TranscriptSource
from loushang.harnesstui.status.line import (
    StatusLinePreviewSnapshot,
    StatusLineSettings,
    status_line_fields,
    status_line_separator,
    status_line_style_mode,
)
from loushang.tui import (
    BottomFrame,
    Composer,
    LoushangWelcomePanel,
    PendingQueueView,
    PendingSection,
    RenderConstraints,
    RenderLine,
    RenderRequestKind,
    RenderResult,
    ScreenLayout,
    StatusBar,
    Surface,
    SurfaceHost,
    TerminalRuntimeCapabilities,
    WorkingLine,
    loushang_welcome_theme,
    theme_capabilities_from_runtime,
)
from loushang.tui.core import RenderLineSegment, SegmentedRenderLines
from loushang.tui.markdown.renderer import MarkdownRenderCache
from loushang.tui.theme import ThemeResolver
from loushang.tui.transcript import (
    AssistantMessageRecord,
    ContextCompactionRecord,
    DisplayRecord,
    ErrorRecord,
    StatusRecord,
    StreamingTextBuffer,
    ThinkingRecord,
    ToolExecutionRecord,
    TranscriptView,
    UserPromptRecord,
    WorkedDividerRecord,
    _prefix_streaming_assistant_segment,
    _render_streaming_assistant_markdown_segments,
)

ACTIVE_RENDER_INTERVAL_MS = 80
DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET = 320
DEFAULT_STABLE_RENDER_CACHE_ENTRY_LIMIT = 128


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


@dataclass(slots=True)
class ScreenCodingTuiApp:
    model_label: str | None
    cwd: str
    branch: str | None
    session_label: str | None
    now: Callable[[], float] = time.monotonic
    composer: Composer = field(default_factory=lambda: Composer(prompt="› ", continuation_prompt="  "))
    state: ScreenCodingTuiState = field(init=False)
    active_surface: Any | None = None
    surface_host: SurfaceHost | None = None
    transcript_theme: ThemeResolver = field(default_factory=_terminal_transcript_theme)
    welcome_theme: ThemeResolver | None = field(default_factory=loushang_welcome_theme)
    active_transcript_line_budget: int = DEFAULT_ACTIVE_TRANSCRIPT_LINE_BUDGET
    stable_render_cache_entry_limit: int = DEFAULT_STABLE_RENDER_CACHE_ENTRY_LIMIT
    render_requester: Callable[[RenderRequestKind], object] | None = None
    terminal_diagnostics_provider: Callable[[], str] | None = None
    terminal_capabilities: TerminalRuntimeCapabilities | None = None
    transcript_source_factory: Callable[[], TranscriptSource] | None = None
    _transcript_region: _ScreenTranscriptRegion = field(init=False, repr=False)
    _bottom_frame_component: BottomFrame = field(init=False, repr=False)
    _render_baseline_reset_reason: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.state = ScreenCodingTuiState(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
        )
        self._transcript_region = _ScreenTranscriptRegion(theme=self.transcript_theme)
        self._bottom_frame_component = BottomFrame(composer=self.composer)

    def start_prompt(self, text: str, *, started_at: float | None = None) -> None:
        self.state.start_prompt(text, started_at=self.now() if started_at is None else started_at)
        self.composer.add_history(text)
        self.composer.clear()

    def start_pending_prompt(self, text: str, *, started_at: float | None = None) -> None:
        self.state.start_prompt(text, started_at=self.now() if started_at is None else started_at)
        self.composer.add_history(text)

    def begin_run(self, *, started_at: float | None = None) -> None:
        self.state.begin_run(started_at=self.now() if started_at is None else started_at)

    def begin_assistant(self) -> None:
        self.state.begin_assistant()
        self._transcript_region.clear_transient_cache()
        self._request_render("product")

    def append_assistant_chunk(self, chunk: str) -> None:
        self.state.append_assistant_chunk(chunk)
        self._request_render("stream")

    def end_assistant(self, final_text: str | None = None) -> None:
        draft_buffer = self.state.assistant_draft_buffer
        draft_text = final_text
        if draft_text is None and draft_buffer is not None:
            draft_text = draft_buffer.text
        self.state.end_assistant(draft_text)
        committed = self.state.records[-1] if self.state.records else None
        if isinstance(committed, AssistantMessageRecord) and committed.text == draft_text:
            self._transcript_region.promote_transient_cache(committed, source_buffer=draft_buffer)
        self._transcript_region.clear_transient_cache()

    def complete_run(self, *, elapsed_seconds: float | None = None) -> None:
        elapsed = self.elapsed_seconds() if elapsed_seconds is None else elapsed_seconds
        self.state.complete_run(elapsed_seconds=elapsed)
        self._transcript_region.clear_transient_cache()

    def queue_followup(self, text: str) -> None:
        self.state.queue_followup(text)

    def queue_steer(self, text: str) -> None:
        self.state.queue_steer(text)

    def sync_queues(self, *, steers: tuple[str, ...] | list[str], followups: tuple[str, ...] | list[str]) -> None:
        self.state.sync_queues(steers=steers, followups=followups)

    def set_status(self, message: str | None) -> None:
        self.state.set_status(message)
        self._request_render("product")

    def set_statusline_visible(self, visible: bool) -> None:
        self.set_statusline_settings(replace(self.state.statusline_settings, enabled=visible))

    def set_statusline_settings(self, settings: StatusLineSettings) -> None:
        self.state.statusline_settings = settings
        self.state.statusline_visible = settings.enabled
        self._request_render("product")

    def request_render(self, kind: RenderRequestKind = "product") -> None:
        self._request_render(kind)

    def statusline_preview_snapshot(self) -> StatusLinePreviewSnapshot:
        return StatusLinePreviewSnapshot(
            model_label=self.state.model_label,
            cwd=self.state.cwd,
            branch=self.state.branch,
            session_label=self.state.session_label,
            running=self.state.running,
            pending_followups=len(self.state.pending_followups),
            pending_steers=len(self.state.pending_steers),
            status_message=self.state.status_message,
        )

    def open_transcript_reader(self) -> bool:
        if self.surface_host is None:
            return False
        source = (
            self.transcript_source_factory()
            if self.transcript_source_factory is not None
            else ActiveWindowTranscriptSource(self.state)
        )
        reader = TranscriptReaderSurface(source)
        self.surface_host.open_surface(
            Surface(
                renderable=reader,
                focus_target=reader,
                presentation="modal",
                max_height="100%",
            )
        )
        self._request_render("input")
        return True

    def add_error(self, summary: str, diagnostics: str = "") -> None:
        self.state.add_error(summary, diagnostics)
        self._request_render("product")

    def add_status(self, message: str) -> None:
        self.state.add_status(message)
        self._request_render("product")

    def replace_transcript_window(
        self,
        records: Iterable[DisplayRecord] | ScreenTranscriptWindow,
        *,
        evicted_prefix_record_count: int = 0,
        reason: str = "replace",
    ) -> None:
        self.state.replace_transcript_window(
            records,
            evicted_prefix_record_count=evicted_prefix_record_count,
        )
        self._render_baseline_reset_reason = f"transcript_window_replaced:{reason}" if reason else "transcript_window_replaced"

    def compact_transcript_window(self, *, summary: str, max_records: int = 80) -> None:
        summary_record = AssistantMessageRecord(f"Compacted summary:\n\n{summary.strip()}")
        active_records = tuple(self.state.records)
        keep_count = max(0, max_records - 1)
        kept_records = active_records[-keep_count:] if keep_count else ()
        evicted_count = max(0, len(active_records) - len(kept_records))
        self.replace_transcript_window(
            (summary_record, *kept_records),
            evicted_prefix_record_count=self.state.evicted_prefix_record_count + evicted_count,
            reason="compaction",
        )

    def append_context_compaction_record(
        self,
        *,
        summary: str = "",
        tokens_before: int | None = None,
        max_records: int = 80,
    ) -> None:
        self.state.records.append(ContextCompactionRecord(summary=summary, tokens_before=tokens_before))
        self.state.mark_records_changed()
        evicted = self.state.trim_transcript_prefix(max_records=max_records)
        if evicted:
            self._render_baseline_reset_reason = "transcript_window_trimmed:context_compaction"

    def consume_render_baseline_reset_reason(self) -> str | None:
        reason = self._render_baseline_reset_reason
        self._render_baseline_reset_reason = None
        return reason

    def elapsed_seconds(self) -> float:
        if self.state.active_started_at is None:
            return 0.0
        return max(0.0, self.now() - self.state.active_started_at)

    def next_frame_due_ms(self, *, after_ms: int) -> int | None:
        completion_due_ms = self.composer.next_frame_due_ms(after_ms=after_ms)
        if not self.state.running:
            return completion_due_ms
        active_due_ms = after_ms + ACTIVE_RENDER_INTERVAL_MS
        if completion_due_ms is None:
            return active_due_ms
        return min(active_due_ms, completion_due_ms)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        visible_height = constraints.visible_height or constraints.max_height
        editor_height = self._bottom_frame_height(visible_height)
        self._transcript_region.records = self.state.records
        self._transcript_region.records_revision = self.state.records_revision
        self._transcript_region.draft = None
        self._transcript_region.draft_buffer = self.state.assistant_draft_buffer
        self._transcript_region.cwd = self.state.cwd
        self._transcript_region.theme = self.transcript_theme
        self._transcript_region.capabilities = (
            theme_capabilities_from_runtime(self.terminal_capabilities) if self.terminal_capabilities is not None else None
        )
        self._transcript_region.window_generation = self.state.transcript_window_generation
        self._transcript_region.stable_cache_entry_limit = self.stable_render_cache_entry_limit
        layout = ScreenLayout(
            transcript=self._transcript_region,
            editor=_CappedRenderable(self._bottom_frame(), max_height=editor_height),
            editor_min_height=editor_height,
        )
        return layout.render(constraints)

    def startup_welcome_panel(self) -> LoushangWelcomePanel:
        return LoushangWelcomePanel(
            directory=self.state.cwd,
            session=self.state.session_label or "",
            model=self.state.model_label or "",
            theme=self.welcome_theme,
        )

    def trim_active_transcript_window(self) -> None:
        records, evicted_count, changed = _trim_records_to_line_budget(
            tuple(self.state.records),
            line_budget=self.active_transcript_line_budget,
        )
        if not changed:
            return
        self.state.replace_transcript_window(
            ScreenTranscriptWindow(
                records=records,
                evicted_prefix_record_count=self.state.evicted_prefix_record_count + evicted_count,
            )
        )
        self._render_baseline_reset_reason = "transcript_window_trimmed:active_line_budget"

    def _expanded_bottom_frame(self) -> bool:
        return (
            self.active_surface is not None
            or self.state.running
            or bool(self.state.pending_steers)
            or bool(self.state.pending_followups)
            or bool(self.state.interruption_message)
        )

    def _bottom_frame_height(self, visible_height: int) -> int:
        height = 12
        if self._expanded_bottom_frame():
            height = 16
            preferred = getattr(self.active_surface, "preferred_height", None)
            if isinstance(preferred, int) and preferred > 0:
                height = max(height, preferred)
        return max(1, min(height, visible_height))

    def _request_render(self, kind: RenderRequestKind) -> None:
        if self.render_requester is not None:
            self.render_requester(kind)

    def _bottom_frame(self) -> BottomFrame:
        self._bottom_frame_component.composer = self.composer
        self._bottom_frame_component.surface = self.active_surface
        self._bottom_frame_component.working_line = self._working_line()
        self._bottom_frame_component.pending_queue = self._pending_queue()
        self._bottom_frame_component.status_bar = self._status_bar() if self.state.statusline_visible else None
        return self._bottom_frame_component

    def _working_line(self) -> WorkingLine | None:
        if not self.state.running:
            return None
        return WorkingLine(label="Working", elapsed_seconds=self.elapsed_seconds())

    def _pending_queue(self) -> PendingQueueView | None:
        sections: list[PendingSection] = []
        if self.state.interruption_message:
            sections.append(
                PendingSection(
                    label=self.state.interruption_message,
                    marker="■",
                    show_when_empty=True,
                )
            )
        if self.state.pending_steers:
            sections.append(
                PendingSection(
                    label="Messages to be submitted after next tool call",
                    items=tuple(self.state.pending_steers),
                    hint="press esc to interrupt and send immediately",
                    hint_placement="header",
                )
            )
        if self.state.pending_followups:
            sections.append(
                PendingSection(
                    label="Queued follow-up inputs",
                    items=tuple(self.state.pending_followups),
                    hint="alt + ↑ edit last queued message",
                )
            )
        if not sections:
            return None
        return PendingQueueView(sections=tuple(sections))

    def _status_bar(self) -> StatusBar:
        settings = self.state.statusline_settings
        return StatusBar(
            status_line_fields(self.statusline_preview_snapshot(), settings),
            separator=status_line_separator(settings),
            style_mode=status_line_style_mode(settings),
        )


@dataclass(slots=True)
class _ScreenTranscriptRegion:
    records: list[DisplayRecord] = field(default_factory=list)
    records_revision: int = 0
    draft: AssistantMessageRecord | None = None
    draft_buffer: StreamingTextBuffer | None = None
    cwd: str = ""
    theme: ThemeResolver | None = None
    capabilities: Any | None = None
    window_generation: int = 0
    stable_cache_entry_limit: int = DEFAULT_STABLE_RENDER_CACHE_ENTRY_LIMIT
    _stable_line_cache: dict[tuple[DisplayRecord, int, tuple[object, ...]], tuple[str, ...]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _transient_line_cache_key: tuple[DisplayRecord, int, tuple[object, ...]] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _transient_line_cache_lines: tuple[str, ...] | None = field(default=None, init=False, repr=False)
    _transient_source_text: str = field(default="", init=False, repr=False)
    _transient_source_width: int = field(default=0, init=False, repr=False)
    _transient_source_style_signature: tuple[object, ...] | None = field(default=None, init=False, repr=False)
    _transient_source_buffer_id: int | None = field(default=None, init=False, repr=False)
    _transient_source_buffer_version: int = field(default=-1, init=False, repr=False)
    _markdown_render_cache: MarkdownRenderCache = field(default_factory=MarkdownRenderCache, init=False, repr=False)
    _cache_generation: int = field(default=-1, init=False, repr=False)
    _committed_segment_key: tuple[object, ...] | None = field(default=None, init=False, repr=False)
    _committed_segment: RenderLineSegment | None = field(default=None, init=False, repr=False)
    _committed_separator_rows: frozenset[int] = field(
        default_factory=frozenset,
        init=False,
        repr=False,
    )
    _draft_segments_key: tuple[object, ...] | None = field(default=None, init=False, repr=False)
    _draft_segments: tuple[RenderLineSegment, ...] = field(default=(), init=False, repr=False)
    _draft_stream_context: tuple[object, ...] | None = field(default=None, init=False, repr=False)
    _draft_stable_segment_cache: dict[tuple[object, ...], RenderLineSegment] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _draft_separator_identity: object = field(default_factory=object, init=False, repr=False)
    _draft_separator_segment: RenderLineSegment | None = field(default=None, init=False, repr=False)
    _draft_has_leading_separator: bool = field(default=False, init=False, repr=False)
    _segmented_transient_content_segments: tuple[RenderLineSegment, ...] = field(
        default=(),
        init=False,
        repr=False,
    )
    _segmented_transient_buffer_id: int | None = field(default=None, init=False, repr=False)
    _segmented_transient_buffer_version: int = field(default=-1, init=False, repr=False)
    _segmented_transient_width: int = field(default=0, init=False, repr=False)
    _segmented_transient_style_signature: tuple[object, ...] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    @property
    def has_content(self) -> bool:
        return bool(self.records or self.draft is not None or self.draft_buffer is not None)

    def render(self, constraints: RenderConstraints) -> RenderResult:
        self._reset_cache_if_window_changed()
        style_signature = (*_screen_transcript_style_signature(self.theme, self.capabilities), self.cwd)
        lines = self._render_tail_segments(
            max_height=constraints.max_height,
            width=constraints.width,
            style_signature=style_signature,
        )
        return RenderResult(lines=lines)

    def _render_record_lines(
        self,
        record: DisplayRecord | StreamingTextBuffer,
        *,
        width: int,
        style_signature: tuple[object, ...],
    ) -> tuple[str, ...]:
        if isinstance(record, StreamingTextBuffer):
            return self._render_streaming_buffer_lines(record, width=width, style_signature=style_signature)
        if isinstance(record, AssistantMessageRecord) and not record.stable:
            return self._render_transient_record_lines(record, width=width, style_signature=style_signature)

        key = (record, width, style_signature)
        cached = self._stable_line_cache.get(key)
        if cached is not None:
            return cached
        rendered = self._render_record_uncached(record, width=width)
        self._stable_line_cache[key] = rendered
        self._enforce_stable_cache_entry_limit()
        return rendered

    def _render_streaming_buffer_lines(
        self,
        buffer: StreamingTextBuffer,
        *,
        width: int,
        style_signature: tuple[object, ...],
    ) -> tuple[str, ...]:
        if (
            self._transient_line_cache_lines is not None
            and self._transient_source_width == width
            and self._transient_source_style_signature == style_signature
            and self._transient_source_buffer_id == id(buffer)
            and self._transient_source_buffer_version == buffer.version
        ):
            return self._transient_line_cache_lines

        rendered = self._render_record_uncached(
            AssistantMessageRecord(_streaming_buffer_render_text(buffer), stable=False),
            width=width,
            markdown_streaming_key=buffer,
        )
        self._remember_streaming_buffer_cache(
            buffer,
            width=width,
            style_signature=style_signature,
            lines=rendered,
        )
        return rendered

    def _render_transient_record_lines(
        self,
        record: AssistantMessageRecord,
        *,
        width: int,
        style_signature: tuple[object, ...],
    ) -> tuple[str, ...]:
        key = (record, width, style_signature)
        if key == self._transient_line_cache_key and self._transient_line_cache_lines is not None:
            return self._transient_line_cache_lines

        rendered = self._render_record_uncached(record, width=width)
        self._transient_line_cache_key = key
        self._transient_line_cache_lines = rendered
        self._transient_source_text = record.text
        self._transient_source_width = width
        self._transient_source_style_signature = style_signature
        self._transient_source_buffer_id = None
        self._transient_source_buffer_version = -1
        return rendered

    def _render_record_uncached(
        self,
        record: DisplayRecord,
        *,
        width: int,
        markdown_streaming_key: object | None = None,
    ) -> tuple[str, ...]:
        display_record = _screen_coding_display_record(record, cwd=self.cwd)
        render_width = _screen_transcript_record_render_width(display_record, width=width)
        view = TranscriptView(
            [display_record],
            theme=self.theme,
            capabilities=self.capabilities,
            markdown_cache=self._markdown_render_cache,
            markdown_streaming_key=markdown_streaming_key,
        )
        rendered = view.render(RenderConstraints(width=render_width, max_height=1_000_000))
        return _coding_lines(
            tuple(line.text for line in rendered.lines),
            display_record,
            theme=self.theme,
            capabilities=self.capabilities,
        )

    def _remember_streaming_buffer_cache(
        self,
        buffer: StreamingTextBuffer,
        *,
        width: int,
        style_signature: tuple[object, ...],
        lines: tuple[str, ...],
    ) -> None:
        self._transient_line_cache_key = None
        self._transient_line_cache_lines = lines
        self._transient_source_text = ""
        self._transient_source_width = width
        self._transient_source_style_signature = style_signature
        self._transient_source_buffer_id = id(buffer)
        self._transient_source_buffer_version = buffer.version

    def _render_tail_rows(
        self,
        *,
        max_height: int,
        width: int,
        style_signature: tuple[object, ...],
    ) -> list[str]:
        return [
            line.text
            for line in self._render_tail_segments(
                max_height=max_height,
                width=width,
                style_signature=style_signature,
            )
        ]

    def _render_tail_segments(
        self,
        *,
        max_height: int,
        width: int,
        style_signature: tuple[object, ...],
    ) -> SegmentedRenderLines:
        if max_height <= 0:
            return SegmentedRenderLines()

        committed = self._render_committed_segment(width=width, style_signature=style_signature)
        draft_segments = self._render_draft_segments(
            width=width,
            style_signature=style_signature,
            has_committed=committed is not None,
        )
        segments = (
            *((committed,) if committed is not None else ()),
            *draft_segments,
        )
        lines = SegmentedRenderLines.from_segments(segments)
        if len(lines) <= max_height:
            return lines

        start = len(lines) - max_height
        committed_rows = committed.line_count if committed is not None else 0
        starts_at_draft_separator = (
            committed is not None
            and bool(draft_segments)
            and self._draft_has_leading_separator
            and start == committed_rows
        )
        if start in self._committed_separator_rows or starts_at_draft_separator:
            start += 1
        return lines[start:]

    def _render_committed_segment(
        self,
        *,
        width: int,
        style_signature: tuple[object, ...],
    ) -> RenderLineSegment | None:
        first_record_id = id(self.records[0]) if self.records else 0
        last_record_id = id(self.records[-1]) if self.records else 0
        key = (
            id(self.records),
            self.records_revision,
            len(self.records),
            first_record_id,
            last_record_id,
            self.window_generation,
            width,
            style_signature,
        )
        if key == self._committed_segment_key:
            return self._committed_segment

        rows: list[str] = []
        separator_rows: set[int] = set()
        for record in self.records:
            block = self._render_record_lines(record, width=width, style_signature=style_signature)
            if not block:
                continue
            if rows:
                separator_rows.add(len(rows))
                rows.append("")
            rows.extend(block)
        segment = (
            RenderLineSegment(
                lines=tuple(RenderLine(row) for row in rows),
                revision=key,
            )
            if rows
            else None
        )
        self._committed_segment_key = key
        self._committed_segment = segment
        self._committed_separator_rows = frozenset(separator_rows)
        return segment

    def _render_draft_segments(
        self,
        *,
        width: int,
        style_signature: tuple[object, ...],
        has_committed: bool,
    ) -> tuple[RenderLineSegment, ...]:
        draft: DisplayRecord | StreamingTextBuffer | None = self.draft_buffer or self.draft
        if draft is None:
            self._clear_draft_segment_cache()
            return ()
        source_revision: object
        if isinstance(draft, StreamingTextBuffer):
            source_revision = (id(draft), draft.version)
        else:
            source_revision = draft
        key = (
            source_revision,
            has_committed,
            self.window_generation,
            width,
            style_signature,
        )
        if key == self._draft_segments_key:
            return self._draft_segments

        if isinstance(draft, StreamingTextBuffer):
            segmented = self._render_streaming_draft_segments(
                draft,
                width=width,
                style_signature=style_signature,
                has_committed=has_committed,
            )
            if segmented is not None:
                self._draft_segments_key = key
                self._draft_segments = segmented
                return segmented

        block = self._render_record_lines(draft, width=width, style_signature=style_signature)
        rows = (("", *block) if has_committed and block else block)
        segment = (
            RenderLineSegment(
                lines=tuple(RenderLine(row) for row in rows),
                revision=key,
            )
            if rows
            else None
        )
        segments = (segment,) if segment is not None else ()
        self._draft_segments_key = key
        self._draft_segments = segments
        self._draft_has_leading_separator = bool(has_committed and block)
        self._segmented_transient_content_segments = ()
        self._segmented_transient_buffer_id = None
        self._segmented_transient_buffer_version = -1
        return segments

    def _render_streaming_draft_segments(
        self,
        buffer: StreamingTextBuffer,
        *,
        width: int,
        style_signature: tuple[object, ...],
        has_committed: bool,
    ) -> tuple[RenderLineSegment, ...] | None:
        stream_context = (
            id(buffer),
            self.window_generation,
            width,
            style_signature,
        )
        if stream_context != self._draft_stream_context:
            self._draft_stream_context = stream_context
            self._draft_stable_segment_cache.clear()
            self._draft_separator_segment = None

        source = _streaming_buffer_render_text(buffer)
        rendered = _render_streaming_assistant_markdown_segments(
            source,
            width=width,
            theme=self.theme,
            capabilities=self.capabilities,
            code_highlighter=None,
            markdown_cache=self._markdown_render_cache,
            markdown_streaming_key=buffer,
        )
        if rendered is None:
            self._draft_stable_segment_cache.clear()
            self._draft_separator_segment = None
            self._segmented_transient_content_segments = ()
            self._segmented_transient_buffer_id = None
            self._segmented_transient_buffer_version = -1
            return None

        content_segments: list[RenderLineSegment] = []
        first_prefix_available = True
        display_record = AssistantMessageRecord(source, stable=False)
        for markdown_segment in rendered.segments:
            has_nonblank = markdown_segment.has_nonblank
            use_first_prefix = first_prefix_available and has_nonblank
            if has_nonblank:
                first_prefix_available = False
            cache_key = (
                markdown_segment.identity,
                markdown_segment.revision,
                use_first_prefix,
            )
            segment = (
                self._draft_stable_segment_cache.get(cache_key)
                if markdown_segment.stable
                else None
            )
            if segment is None:
                prefixed = _prefix_streaming_assistant_segment(
                    markdown_segment.lines,
                    width=width,
                    use_first_prefix=use_first_prefix,
                )
                coding_lines = _coding_lines(
                    prefixed,
                    display_record,
                    theme=self.theme,
                    capabilities=self.capabilities,
                )
                segment = RenderLineSegment(
                    lines=tuple(RenderLine(line) for line in coding_lines),
                    identity=("streaming-markdown", markdown_segment.identity),
                    revision=(markdown_segment.revision, use_first_prefix),
                )
                if markdown_segment.stable:
                    self._draft_stable_segment_cache[cache_key] = segment
            content_segments.append(segment)

        content = tuple(content_segments)
        segments: tuple[RenderLineSegment, ...] = content
        if has_committed and content:
            if self._draft_separator_segment is None:
                self._draft_separator_segment = RenderLineSegment(
                    lines=(RenderLine(""),),
                    identity=self._draft_separator_identity,
                    revision=stream_context,
                )
            segments = (self._draft_separator_segment, *content)
        self._draft_has_leading_separator = bool(has_committed and content)

        self._segmented_transient_content_segments = content
        self._segmented_transient_buffer_id = id(buffer)
        self._segmented_transient_buffer_version = buffer.version
        self._segmented_transient_width = width
        self._segmented_transient_style_signature = style_signature
        return segments

    def _clear_draft_segment_cache(self) -> None:
        self._draft_segments_key = None
        self._draft_segments = ()
        self._draft_stream_context = None
        self._draft_stable_segment_cache.clear()
        self._draft_separator_segment = None
        self._draft_has_leading_separator = False
        self._segmented_transient_content_segments = ()
        self._segmented_transient_buffer_id = None
        self._segmented_transient_buffer_version = -1
        self._segmented_transient_width = 0
        self._segmented_transient_style_signature = None

    def _iter_records(self) -> Iterable[DisplayRecord | StreamingTextBuffer]:
        yield from self.records
        if self.draft_buffer is not None:
            yield self.draft_buffer
        elif self.draft is not None:
            yield self.draft

    def _reset_cache_if_window_changed(self) -> None:
        if self._cache_generation == self.window_generation:
            return
        self._stable_line_cache.clear()
        self._transient_line_cache_key = None
        self._transient_line_cache_lines = None
        self._markdown_render_cache.clear()
        self._committed_segment_key = None
        self._committed_segment = None
        self._committed_separator_rows = frozenset()
        self._clear_draft_segment_cache()
        self._cache_generation = self.window_generation

    def clear_transient_cache(self) -> None:
        self._transient_line_cache_key = None
        self._transient_line_cache_lines = None
        self._transient_source_text = ""
        self._transient_source_width = 0
        self._transient_source_style_signature = None
        self._transient_source_buffer_id = None
        self._transient_source_buffer_version = -1
        self._clear_draft_segment_cache()
        self._markdown_render_cache.clear_streaming()

    def promote_transient_cache(
        self,
        record: AssistantMessageRecord,
        *,
        source_buffer: StreamingTextBuffer | None = None,
    ) -> None:
        if source_buffer is not None and self._segmented_transient_content_segments:
            if self._segmented_transient_buffer_id != id(source_buffer):
                return
            if self._segmented_transient_buffer_version != source_buffer.version:
                return
            if record.text != source_buffer.text:
                return
            if (
                self._segmented_transient_width <= 0
                or self._segmented_transient_style_signature is None
            ):
                return
            canonical_lines = tuple(
                line.text
                for segment in self._segmented_transient_content_segments
                for line in segment.lines
            )
            self._stable_line_cache[
                (
                    record,
                    self._segmented_transient_width,
                    self._segmented_transient_style_signature,
                )
            ] = canonical_lines
            self._enforce_stable_cache_entry_limit()
            return
        if self._transient_line_cache_lines is None:
            return
        if source_buffer is None and record.text != self._transient_source_text:
            return
        if source_buffer is not None and self._transient_source_buffer_id != id(source_buffer):
            return
        if source_buffer is not None and self._transient_source_buffer_version != source_buffer.version:
            return
        if self._transient_source_width <= 0 or self._transient_source_style_signature is None:
            return
        canonical_lines = self._render_record_uncached(record, width=self._transient_source_width)
        self._stable_line_cache[
            (record, self._transient_source_width, self._transient_source_style_signature)
        ] = canonical_lines
        self._enforce_stable_cache_entry_limit()

    def _enforce_stable_cache_entry_limit(self) -> None:
        limit = max(0, self.stable_cache_entry_limit)
        if limit == 0:
            self._stable_line_cache.clear()
            return
        while len(self._stable_line_cache) > limit:
            self._stable_line_cache.pop(next(iter(self._stable_line_cache)))


@dataclass(frozen=True, slots=True)
class _CappedRenderable:
    renderable: Any
    max_height: int

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return self.renderable.render(
            RenderConstraints(
                width=constraints.width,
                max_height=max(1, min(self.max_height, constraints.max_height)),
                visible_height=constraints.visible_height,
            )
        )


def _coding_line(
    line: str,
    record: DisplayRecord,
    *,
    theme: ThemeResolver | None,
    capabilities: Any | None,
) -> str:
    if isinstance(record, UserPromptRecord) and line.startswith("> "):
        line = "› " + line[2:]
        return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
    if isinstance(record, AssistantMessageRecord) and line.startswith("* "):
        line = "• " + line[2:]
        return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
    if isinstance(record, ErrorRecord) and line.startswith("! Error: "):
        line = "■ Error: " + line[len("! Error: ") :]
        return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
    if isinstance(record, ContextCompactionRecord) and line.startswith("* "):
        line = "• " + line[2:]
        return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
    if isinstance(record, ToolExecutionRecord):
        if line.startswith("- Ran "):
            line = "• Ran " + line[len("- Ran ") :]
            return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
        if line.startswith("! Ran "):
            line = "■ Ran " + line[len("! Ran ") :]
            return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
        return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
    if isinstance(record, WorkedDividerRecord) and line.startswith("- Worked for "):
        line = line.replace("-", "─", 1).replace("-", "─")
        return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)
    return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)


def _screen_coding_display_record(record: DisplayRecord, *, cwd: str = "") -> DisplayRecord:
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


def _coding_lines(
    lines: tuple[str, ...],
    record: DisplayRecord,
    *,
    theme: ThemeResolver | None,
    capabilities: Any | None,
) -> tuple[str, ...]:
    if not isinstance(record, ToolExecutionRecord):
        return tuple(_coding_line(line, record, theme=theme, capabilities=capabilities) for line in lines)

    rendered: list[str] = []
    output_started = False
    for line in lines:
        if line.startswith("- Ran ") or line.startswith("! Ran "):
            rendered.append(_coding_line(line, record, theme=theme, capabilities=capabilities))
            continue
        if line.startswith("  $ "):
            rendered.append(_style_tool_body_line(f"  │ {line[2:]}", record, theme=theme, capabilities=capabilities))
            continue
        if line.startswith("  "):
            content = line[2:]
            prefix = "  └ " if not output_started else "    "
            output_started = True
            rendered.append(_style_tool_body_line(f"{prefix}{content}", record, theme=theme, capabilities=capabilities))
            continue
        rendered.append(_coding_line(line, record, theme=theme, capabilities=capabilities))
    return tuple(rendered)


def _style_tool_body_line(
    line: str,
    record: ToolExecutionRecord,
    *,
    theme: ThemeResolver | None,
    capabilities: Any | None,
) -> str:
    return apply_coding_transcript_style(line, record, theme=theme, capabilities=capabilities)


def _screen_transcript_record_render_width(record: DisplayRecord, *, width: int) -> int:
    if isinstance(record, ToolExecutionRecord):
        return max(1, width - 2)
    return width


def _streaming_buffer_render_text(buffer: StreamingTextBuffer) -> str:
    return "\n".join(buffer.logical_lines())


def _screen_transcript_style_signature(theme: ThemeResolver | None, capabilities: Any | None) -> tuple[object, ...]:
    capabilities_signature: tuple[bool, bool] | None = None
    if capabilities is not None:
        capabilities_signature = (bool(capabilities.truecolor), bool(capabilities.hyperlinks))
    if theme is None:
        return (None, capabilities_signature)
    return (id(theme), theme.version, capabilities_signature)


def _trim_records_to_line_budget(
    records: tuple[DisplayRecord, ...],
    *,
    line_budget: int,
) -> tuple[tuple[DisplayRecord, ...], int, bool]:
    line_budget = max(0, line_budget)
    if not records or line_budget <= 0:
        return (), len(records), bool(records)

    kept_newest_first: list[DisplayRecord] = []
    used_lines = 0
    fully_evicted_count = 0
    changed = False

    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        separator_lines = 1 if kept_newest_first else 0
        available = line_budget - used_lines - separator_lines
        if available <= 0:
            fully_evicted_count = index + 1
            changed = True
            break

        record_lines = _record_logical_line_count(record)
        if record_lines <= available:
            kept_newest_first.append(record)
            used_lines += separator_lines + record_lines
            continue

        trimmed = _tail_trim_record(record, max_lines=available)
        if trimmed is not None:
            kept_newest_first.append(trimmed)
            used_lines += separator_lines + _record_logical_line_count(trimmed)
            fully_evicted_count = index
        else:
            fully_evicted_count = index + 1
        changed = True
        break

    kept_records = tuple(reversed(kept_newest_first))
    if not changed and len(kept_records) == len(records):
        return records, 0, False
    return kept_records, fully_evicted_count, True


def _record_logical_line_count(record: DisplayRecord) -> int:
    if isinstance(record, UserPromptRecord | AssistantMessageRecord | ThinkingRecord | StatusRecord):
        return _text_line_count(record.text)
    if isinstance(record, ToolExecutionRecord):
        count = 1
        if record.command:
            count += _text_line_count(record.command)
        if record.output:
            count += _text_line_count(record.output)
        if record.stderr:
            count += _text_line_count(record.stderr)
        if record.exit_code is not None:
            count += 1
        return count
    if isinstance(record, ErrorRecord):
        return 1 + (_text_line_count(record.diagnostics) if record.diagnostics else 0)
    return 1


def _text_line_count(text: str) -> int:
    if not text:
        return 1
    return max(1, text.count("\n") + (0 if text.endswith("\n") else 1))


def _tail_trim_record(record: DisplayRecord, *, max_lines: int) -> DisplayRecord | None:
    if max_lines <= 0:
        return None
    if isinstance(record, UserPromptRecord):
        return UserPromptRecord(
            _tail_trim_text(
                record.text,
                max_lines=max_lines,
                marker="[older prompt content omitted from active UI window]",
            )
        )
    if isinstance(record, AssistantMessageRecord):
        return AssistantMessageRecord(
            _tail_trim_text(
                record.text,
                max_lines=max_lines,
                marker="[older assistant output omitted from active UI window]",
            ),
            stable=record.stable,
        )
    if isinstance(record, ThinkingRecord):
        return replace(
            record,
            text=_tail_trim_text(
                record.text,
                max_lines=max_lines,
                marker="[older thinking content omitted from active UI window]",
            ),
        )
    if isinstance(record, StatusRecord):
        return StatusRecord(
            _tail_trim_text(
                record.text,
                max_lines=max_lines,
                marker="[older status content omitted from active UI window]",
            )
        )
    if isinstance(record, ErrorRecord):
        if max_lines <= 1 or not record.diagnostics:
            return ErrorRecord("[older error details omitted from active UI window]")
        return replace(
            record,
            diagnostics=_tail_trim_text(
                record.diagnostics,
                max_lines=max_lines - 1,
                marker="[older error diagnostics omitted from active UI window]",
            ),
        )
    if isinstance(record, ToolExecutionRecord):
        return _tail_trim_tool_record(record, max_lines=max_lines)
    return None


def _tail_trim_tool_record(record: ToolExecutionRecord, *, max_lines: int) -> ToolExecutionRecord | None:
    output_budget = max_lines - 1
    if record.command:
        output_budget -= _text_line_count(record.command)
    if record.stderr:
        output_budget -= _text_line_count(record.stderr)
    if record.exit_code is not None:
        output_budget -= 1
    if output_budget <= 0:
        if max_lines <= 1:
            return None
        return replace(record, output="[older tool output omitted from active UI window]", stderr="", command="")
    return replace(
        record,
        output=_tail_trim_text(
            record.output,
            max_lines=output_budget,
            marker="[older tool output omitted from active UI window]",
        ),
    )


def _tail_trim_text(text: str, *, max_lines: int, marker: str) -> str:
    if max_lines <= 1:
        return marker
    if _text_line_count(text) <= max_lines:
        return text
    lines = text.rstrip("\n").rsplit("\n", max_lines - 1)
    return "\n".join([marker, *lines[-(max_lines - 1) :]])


def _cwd_label(cwd: str) -> str:
    if not cwd:
        return "cwd"
    return cwd.rstrip("/").rsplit("/", 1)[-1] or cwd


__all__ = ["ScreenCodingTuiApp"]
