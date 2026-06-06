from __future__ import annotations

from dataclasses import dataclass

from loushang.coding.ui.transcript_reader import TranscriptReaderSurface
from loushang.coding.ui.transcript_source import TranscriptSnapshot
from loushang.tui import RenderConstraints, strip_control_sequences
from loushang.tui.input import InputEvent, InputIntent
from loushang.tui.transcript import (
    AssistantMessageRecord,
    DisplayRecord,
    UserPromptRecord,
)


@dataclass(slots=True)
class _Source:
    records: tuple[DisplayRecord, ...]
    evicted_prefix_record_count: int = 0
    snapshot_calls: int = 0

    def snapshot(self) -> TranscriptSnapshot:
        self.snapshot_calls += 1
        return TranscriptSnapshot(
            records=self.records,
            evicted_prefix_record_count=self.evicted_prefix_record_count,
            complete=False,
            source_label="Transcript window",
        )

    def recent_assistant_texts(self) -> tuple[str, ...]:
        return tuple(record.text for record in reversed(self.records) if isinstance(record, AssistantMessageRecord) and record.text)


def _render_text(reader: TranscriptReaderSurface, *, width: int = 48, height: int = 6) -> tuple[str, ...]:
    result = reader.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text) for line in result.lines)


def test_transcript_reader_renders_frozen_snapshot_and_footer() -> None:
    source = _Source((UserPromptRecord("hello"), AssistantMessageRecord("first")), evicted_prefix_record_count=2)
    reader = TranscriptReaderSurface(source)

    first = _render_text(reader, width=80, height=7)
    source.records = (AssistantMessageRecord("second"),)
    second = _render_text(reader, width=80, height=7)

    assert source.snapshot_calls == 1
    assert first == second
    assert first[0] == "Transcript window"
    assert "Earlier transcript records were trimmed." in first
    assert first[-1] == "Ctrl+O/q/Esc close | PgUp/PgDn scroll | d detail | r raw"
    assert any("first" in line for line in first)
    assert all("second" not in line for line in first)


def test_transcript_reader_opens_at_tail_and_scrolls_by_page() -> None:
    source = _Source((AssistantMessageRecord("\n".join(f"line {index}" for index in range(8))),))
    reader = TranscriptReaderSurface(source)

    tail = _render_text(reader, height=5)
    assert any("line 7" in line for line in tail)
    assert all("line 0" not in line for line in tail)

    assert reader.handle_input(InputEvent(kind="key", key="pageUp")) == InputIntent(kind="consumed", note="transcript_reader")
    older = _render_text(reader, height=5)
    assert any("line 4" in line for line in older)
    assert reader.scroll_offset < reader.max_scroll_offset

    assert reader.handle_input(InputEvent(kind="key", key="end")) == InputIntent(kind="consumed", note="transcript_reader")
    assert any("line 7" in line for line in _render_text(reader, height=5))


def test_transcript_reader_clamps_scroll_offset_after_resize() -> None:
    source = _Source((AssistantMessageRecord("\n".join(f"line {index}" for index in range(6))),))
    reader = TranscriptReaderSurface(source)

    reader.handle_input(InputEvent(kind="key", key="home"))
    _render_text(reader, height=5)
    assert reader.scroll_offset == 0

    reader.handle_input(InputEvent(kind="key", key="end"))
    _render_text(reader, height=5)
    assert reader.scroll_offset == reader.max_scroll_offset

    _render_text(reader, height=12)
    assert reader.scroll_offset == 0
    assert reader.max_scroll_offset == 0


def test_transcript_reader_close_keys_return_surface_close() -> None:
    reader = TranscriptReaderSurface(_Source((AssistantMessageRecord("answer"),)))

    for key in ("q", "esc", "escape", "ctrl+c", "ctrl_c", "ctrl+o", "ctrl_o"):
        assert reader.handle_input(InputEvent(kind="key", key=key)) == InputIntent(kind="surface_close")


def test_transcript_reader_strictly_consumes_unrecognized_input() -> None:
    reader = TranscriptReaderSurface(_Source((AssistantMessageRecord("answer"),)))

    assert reader.handle_input(InputEvent(kind="key", key="tab")) == InputIntent(kind="consumed", note="transcript_reader")
    assert reader.handle_input(InputEvent(kind="text", text="x")) == InputIntent(kind="consumed", note="transcript_reader")


def test_transcript_reader_detail_and_raw_toggles_are_stable() -> None:
    reader = TranscriptReaderSurface(_Source((AssistantMessageRecord("answer"),)))

    assert reader.handle_input(InputEvent(kind="key", key="d")) == InputIntent(kind="consumed", note="transcript_reader")
    assert reader.detail_mode is True
    assert reader.handle_input(InputEvent(kind="key", key="d")) == InputIntent(kind="consumed", note="transcript_reader")
    assert reader.detail_mode is False

    assert reader.handle_input(InputEvent(kind="key", key="r")) == InputIntent(kind="consumed", note="transcript_reader")
    assert reader.raw_mode is True
    assert reader.handle_input(InputEvent(kind="key", key="r")) == InputIntent(kind="consumed", note="transcript_reader")
    assert reader.raw_mode is False
