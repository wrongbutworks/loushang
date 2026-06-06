from __future__ import annotations

from dataclasses import dataclass, field

from loushang.coding.ui.transcript_source import TranscriptSnapshot, TranscriptSource
from loushang.tui.cell_width import truncate_to_width
from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.input import InputEvent, InputIntent
from loushang.tui.transcript import render_transcript_records

_MAX_TRANSCRIPT_RENDER_HEIGHT = 1_000_000
_FOOTER = "Ctrl+O/q/Esc close | PgUp/PgDn scroll | d detail | r raw"
_CONSUMED = InputIntent(kind="consumed", note="transcript_reader")


@dataclass(slots=True)
class TranscriptReaderSurface:
    source: TranscriptSource
    focused: bool = False
    raw_mode: bool = False
    detail_mode: bool = False
    _snapshot: TranscriptSnapshot = field(init=False, repr=False)
    _scroll_offset: int = field(default=0, init=False, repr=False)
    _max_scroll_offset: int = field(default=0, init=False, repr=False)
    _last_body_height: int = field(default=1, init=False, repr=False)
    _follow_tail: bool = field(default=True, init=False, repr=False)

    def __post_init__(self) -> None:
        self._snapshot = self.source.snapshot()

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offset

    @property
    def max_scroll_offset(self) -> int:
        return self._max_scroll_offset

    def focus(self) -> None:
        self.focused = True

    def blur(self) -> None:
        self.focused = False

    def handle_input(self, event: InputEvent) -> InputIntent:
        if event.kind != "key":
            return _CONSUMED
        key = event.key
        if key in {"q", "esc", "escape", "ctrl+c", "ctrl_c", "ctrl+o", "ctrl_o"}:
            return InputIntent(kind="surface_close")
        if key == "up":
            self._scroll_by(-1)
            return _CONSUMED
        if key == "down":
            self._scroll_by(1)
            return _CONSUMED
        if key == "pageUp":
            self._scroll_by(-self._last_body_height)
            return _CONSUMED
        if key == "pageDown":
            self._scroll_by(self._last_body_height)
            return _CONSUMED
        if key == "home":
            self._scroll_to_start()
            return _CONSUMED
        if key == "end":
            self._scroll_to_tail()
            return _CONSUMED
        if key == "d":
            self.detail_mode = not self.detail_mode
            return _CONSUMED
        if key == "r":
            self.raw_mode = not self.raw_mode
            return _CONSUMED
        return _CONSUMED

    def render(self, constraints: RenderConstraints) -> RenderResult:
        chrome = self._chrome_lines(constraints.width, constraints.max_height)
        body_height = max(0, constraints.max_height - len(chrome))
        self._last_body_height = max(1, body_height)
        body = self._body_lines(width=constraints.width)
        self._max_scroll_offset = max(0, len(body) - body_height)
        if self._follow_tail:
            self._scroll_offset = self._max_scroll_offset
        else:
            self._scroll_offset = _clamp(self._scroll_offset, 0, self._max_scroll_offset)

        visible_body = body[self._scroll_offset : self._scroll_offset + body_height] if body_height else ()
        lines = [*chrome[:-1], *visible_body, *chrome[-1:]]
        if len(lines) < constraints.max_height and not visible_body:
            insert_at = max(0, len(lines) - 1)
            lines.insert(insert_at, RenderLine(truncate_to_width("No transcript records.", max_width=constraints.width)))
        return RenderResult.from_lines(lines[: constraints.max_height], constraints=constraints)

    def _chrome_lines(self, width: int, max_height: int) -> tuple[RenderLine, ...]:
        lines = [RenderLine(truncate_to_width(self._snapshot.source_label, max_width=width))]
        if self._snapshot.evicted_prefix_record_count > 0 and len(lines) < max_height - 1:
            lines.append(RenderLine(truncate_to_width("Earlier transcript records were trimmed.", max_width=width)))
        if len(lines) < max_height:
            lines.append(RenderLine(truncate_to_width(_FOOTER, max_width=width)))
        return tuple(lines[:max_height])

    def _body_lines(self, *, width: int) -> tuple[RenderLine, ...]:
        return render_transcript_records(
            self._snapshot.records,
            width=width,
            max_height=_MAX_TRANSCRIPT_RENDER_HEIGHT,
        )

    def _scroll_by(self, delta: int) -> None:
        self._follow_tail = False
        self._scroll_offset = _clamp(self._scroll_offset + delta, 0, self._max_scroll_offset)
        if self._scroll_offset >= self._max_scroll_offset and delta > 0:
            self._follow_tail = True

    def _scroll_to_start(self) -> None:
        self._follow_tail = False
        self._scroll_offset = 0

    def _scroll_to_tail(self) -> None:
        self._follow_tail = True
        self._scroll_offset = self._max_scroll_offset


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


__all__ = ["TranscriptReaderSurface"]
