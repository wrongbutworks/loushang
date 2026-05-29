from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from loushang.tui.terminal import (
    FakeTerminalPort,
    TerminalFrame,
    TerminalOperation,
    TerminalSize,
)


@dataclass(frozen=True, slots=True)
class RenderDiagnostics:
    current_logical_lines: tuple[str, ...]
    previous_rendered_lines: tuple[str, ...] = ()
    changed_line_range: tuple[int, int] | None = None
    operation_class: str | None = None
    append_start: int | None = None
    appended_lines: int = 0
    render_end: int | None = None
    viewport_top: int = 0
    previous_viewport_top: int = 0
    logical_cursor_row: int = 0
    logical_cursor_column: int = 0
    hardware_cursor_row: int = 0
    hardware_cursor_column: int = 0
    working_area_high_water_mark: int = 0
    width_changed: bool = False
    height_changed: bool = False
    operations: tuple[TerminalOperation, ...] = ()
    repaint_kind: str | None = None
    repaint_reason: str | None = None
    clear_scrollback_policy: str = "disabled"
    clear_scrollback_emitted: bool = False


@dataclass(frozen=True, slots=True)
class PlaybackEvent:
    kind: str
    payload: Any = None

    @classmethod
    def resize(cls, *, columns: int, rows: int) -> PlaybackEvent:
        return cls(kind="resize", payload=TerminalSize(columns=columns, rows=rows))

    @classmethod
    def input(cls, chunk: str) -> PlaybackEvent:
        return cls(kind="input", payload=chunk)


@dataclass(frozen=True, slots=True)
class PlaybackStep:
    index: int
    event: PlaybackEvent
    size: TerminalSize
    diagnostics: RenderDiagnostics
    flush_error: str | None = None
    frame: TerminalFrame | None = None

    @property
    def flush_succeeded(self) -> bool:
        return self.flush_error is None

    def assert_operation_class(self, expected: str) -> None:
        actual = self.diagnostics.operation_class
        if actual != expected:
            raise AssertionError(f"expected operation_class {expected!r}, got {actual!r}")

    def assert_no_clear_scrollback(self) -> None:
        if self.diagnostics.clear_scrollback_emitted:
            raise AssertionError("expected diagnostics to report no clear scrollback")
        if self.frame is not None and self.frame.clear_scrollback_emitted:
            raise AssertionError("expected frame to emit no clear scrollback")

    def assert_has_clear_scrollback(self) -> None:
        if not self.diagnostics.clear_scrollback_emitted:
            raise AssertionError("expected diagnostics to report clear scrollback")
        if self.frame is None or not self.frame.clear_scrollback_emitted:
            raise AssertionError("expected frame to emit clear scrollback")


PlaybackRender = Callable[[PlaybackEvent, TerminalSize, RenderDiagnostics | None], RenderDiagnostics]


@dataclass(slots=True)
class PlaybackHarness:
    render: PlaybackRender
    port: FakeTerminalPort = field(default_factory=FakeTerminalPort)
    previous_successful_diagnostics: RenderDiagnostics | None = None
    steps: tuple[PlaybackStep, ...] = ()

    def play(self, events: Iterable[PlaybackEvent]) -> tuple[PlaybackStep, ...]:
        new_steps: list[PlaybackStep] = []
        for event in events:
            if event.kind == "resize":
                if not isinstance(event.payload, TerminalSize):
                    raise TypeError("resize event payload must be TerminalSize")
                self.port.resize(event.payload)

            size = self.port.size()
            diagnostics = self.render(event, size, self.previous_successful_diagnostics)
            diagnostics = _normalize_diagnostics(diagnostics)
            flush_error: str | None = None
            frame: TerminalFrame | None = None
            try:
                frame = self.port.flush(diagnostics.operations)
            except Exception as exc:  # noqa: BLE001 - playback harness records terminal failures.
                flush_error = str(exc)
            else:
                self.previous_successful_diagnostics = diagnostics

            step = PlaybackStep(
                index=len(self.steps) + len(new_steps),
                event=event,
                size=size,
                diagnostics=diagnostics,
                flush_error=flush_error,
                frame=frame,
            )
            new_steps.append(step)

        self.steps = (*self.steps, *new_steps)
        return tuple(new_steps)


def _normalize_diagnostics(diagnostics: RenderDiagnostics) -> RenderDiagnostics:
    clear_scrollback_emitted = any(operation.kind == "clear_scrollback" for operation in diagnostics.operations)
    if diagnostics.clear_scrollback_emitted == clear_scrollback_emitted:
        return diagnostics
    return replace(diagnostics, clear_scrollback_emitted=clear_scrollback_emitted)
