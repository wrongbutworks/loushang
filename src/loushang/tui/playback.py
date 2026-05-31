from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Self

from loushang.tui.cell_width import strip_control_sequences
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


@dataclass(frozen=True, slots=True)
class PlaybackArtifacts:
    trace: Path
    screen: Path


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


@dataclass(frozen=True, slots=True)
class PlaybackResult:
    steps: tuple[PlaybackStep, ...]
    port: FakeTerminalPort

    @property
    def visible_text(self) -> str:
        return strip_control_sequences("\n".join(self.port.screen.visible_lines))

    def assert_all_flush_succeeded(self) -> None:
        failed = [step for step in self.steps if not step.flush_succeeded]
        assert not failed

    def assert_visible_contains(self, expected: str) -> None:
        assert expected in self.visible_text

    def assert_visible_not_contains(self, unexpected: str) -> None:
        assert unexpected not in self.visible_text

    def assert_last_operation_class_not_in(self, *unexpected: str) -> None:
        assert self.steps
        assert self.steps[-1].diagnostics.operation_class not in unexpected

    def assert_operation_classes_not_in(self, *unexpected: str, skip_first: bool = False) -> None:
        unexpected_set = set(unexpected)
        steps = self.steps[1:] if skip_first else self.steps
        for step in steps:
            operation_class = step.diagnostics.operation_class
            if operation_class in unexpected_set:
                raise AssertionError(
                    f"step {step.index} used disallowed operation_class {operation_class!r}"
                )

    def assert_max_operations_per_step(self, max_operations: int, *, skip_first: bool = False) -> None:
        steps = self.steps[1:] if skip_first else self.steps
        for step in steps:
            operation_count = len(step.diagnostics.operations)
            if operation_count > max_operations:
                raise AssertionError(
                    f"step {step.index} emitted {operation_count} operations, expected <= {max_operations}"
                )

    def assert_max_serialized_output_bytes_per_step(
        self,
        max_bytes: int,
        *,
        skip_first: bool = False,
    ) -> None:
        steps = self.steps[1:] if skip_first else self.steps
        for step in steps:
            if step.frame is None:
                if step.flush_error is not None:
                    continue
                raise AssertionError(f"step {step.index} did not record a terminal frame")
            byte_count = len(step.frame.serialized_output.encode("utf-8"))
            if byte_count > max_bytes:
                raise AssertionError(
                    f"step {step.index} emitted {byte_count} serialized bytes, expected <= {max_bytes}"
                )

    def assert_screen_anchor_stable(
        self,
        anchor: str,
        *,
        occurrence: str = "first",
        skip_first: bool = False,
    ) -> None:
        steps = self.steps[1:] if skip_first else self.steps
        if not steps:
            raise AssertionError("expected at least one playback step")
        baseline = _screen_anchor_row(steps[0], anchor, occurrence=occurrence)
        if baseline is None:
            raise AssertionError(f"anchor {anchor!r} was not visible at step {steps[0].index}")
        for step in steps[1:]:
            row = _screen_anchor_row(step, anchor, occurrence=occurrence)
            if row is None:
                raise AssertionError(f"anchor {anchor!r} was not visible at step {step.index}")
            if row != baseline:
                raise AssertionError(
                    f"anchor {anchor!r} moved from row {baseline} to row {row} at step {step.index}"
                )

    def assert_synchronized_frames(self, *, skip_first: bool = False) -> None:
        steps = self.steps[1:] if skip_first else self.steps
        for step in steps:
            if step.frame is None:
                if step.flush_error is not None:
                    continue
                raise AssertionError(f"step {step.index} did not record a terminal frame")
            if not step.frame.synchronized:
                raise AssertionError(f"step {step.index} was not synchronized")

    def assert_no_clear_screen(self) -> None:
        clear_screen = TerminalOperation.clear_screen()
        clear_scrollback = TerminalOperation.clear_scrollback()
        for step in self.steps:
            assert clear_screen not in step.diagnostics.operations
            assert clear_scrollback not in step.diagnostics.operations
            step.assert_no_clear_scrollback()
            if step.frame is not None:
                assert clear_screen.serialize() not in step.frame.serialized_output
                assert clear_scrollback.serialize() not in step.frame.serialized_output

    def assert_no_clear_scrollback(self) -> None:
        clear_scrollback = TerminalOperation.clear_scrollback()
        for step in self.steps:
            assert clear_scrollback not in step.diagnostics.operations
            step.assert_no_clear_scrollback()
            if step.frame is not None:
                assert clear_scrollback.serialize() not in step.frame.serialized_output

    def assert_cursor_matches_diagnostics(self) -> None:
        for step in self.steps:
            assert step.frame is not None
            assert step.frame.screen_after.cursor_row == step.diagnostics.hardware_cursor_row
            assert step.frame.screen_after.cursor_column == step.diagnostics.hardware_cursor_column

    def assert_last_cursor_matches_diagnostics(self) -> None:
        assert self.steps
        step = self.steps[-1]
        assert step.frame is not None
        assert step.frame.screen_after.cursor_row == step.diagnostics.hardware_cursor_row
        assert step.frame.screen_after.cursor_column == step.diagnostics.hardware_cursor_column

    def write_jsonl(self, path: str | Path, *, include_frames: bool = False) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as stream:
            for step in self.steps:
                stream.write(json.dumps(self._jsonl_row(step, include_frames=include_frames), ensure_ascii=False))
                stream.write("\n")

    def write_artifacts(
        self,
        directory: str | Path,
        *,
        basename: str = "playback",
        include_frames: bool = False,
    ) -> PlaybackArtifacts:
        output_dir = Path(directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = output_dir / f"{basename}.jsonl"
        screen_path = output_dir / f"{basename}-screen.txt"
        self.write_jsonl(trace_path, include_frames=include_frames)
        screen_path.write_text(self.visible_text, encoding="utf-8")
        return PlaybackArtifacts(trace=trace_path, screen=screen_path)

    def _jsonl_row(self, step: PlaybackStep, *, include_frames: bool) -> dict[str, Any]:
        serialized_output = step.frame.serialized_output if step.frame is not None else None
        row = {
            "index": step.index,
            "event": _event_payload(step.event),
            "size": {"columns": step.size.columns, "rows": step.size.rows},
            "operation_class": step.diagnostics.operation_class,
            "changed_line_range": list(step.diagnostics.changed_line_range)
            if step.diagnostics.changed_line_range is not None
            else None,
            "hardware_cursor": {
                "row": step.diagnostics.hardware_cursor_row,
                "column": step.diagnostics.hardware_cursor_column,
            },
            "flush_succeeded": step.flush_succeeded,
            "flush_error": step.flush_error,
            "operation_count": len(step.diagnostics.operations),
            "operations": [operation.kind for operation in step.diagnostics.operations],
            "serialized_output_bytes": len(serialized_output.encode("utf-8")) if serialized_output is not None else None,
            "synchronized": step.frame.synchronized if step.frame is not None else None,
            "clear_scrollback_emitted": (
                step.frame.clear_scrollback_emitted
                if step.frame is not None
                else step.diagnostics.clear_scrollback_emitted
            ),
            "visible_lines": list(step.frame.screen_after.visible_lines if step.frame is not None else self.port.screen.visible_lines),
        }
        if include_frames:
            row["serialized_output"] = serialized_output
        return row


@dataclass(slots=True)
class PlaybackScenario:
    _events: list[PlaybackEvent] = field(default_factory=list, init=False)

    @property
    def events(self) -> tuple[PlaybackEvent, ...]:
        return tuple(self._events)

    def type_text(self, text: str) -> Self:
        self._events.append(PlaybackEvent.input(text))
        return self

    def render(self) -> Self:
        self._events.append(PlaybackEvent("render"))
        return self

    def enter(self) -> Self:
        return self.key("\r")

    def tab(self) -> Self:
        return self.key("\t")

    def escape(self) -> Self:
        return self.key("\x1b")

    def ctrl_c(self) -> Self:
        return self.key("\x03")

    def key(self, raw: str) -> Self:
        self._events.append(PlaybackEvent.input(raw))
        return self

    def resize(self, *, width: int, height: int) -> Self:
        self._events.append(PlaybackEvent.resize(columns=width, rows=height))
        return self


def _normalize_diagnostics(diagnostics: RenderDiagnostics) -> RenderDiagnostics:
    clear_scrollback_emitted = any(operation.kind == "clear_scrollback" for operation in diagnostics.operations)
    if diagnostics.clear_scrollback_emitted == clear_scrollback_emitted:
        return diagnostics
    return replace(diagnostics, clear_scrollback_emitted=clear_scrollback_emitted)


def _screen_anchor_row(step: PlaybackStep, anchor: str, *, occurrence: str) -> int | None:
    if occurrence not in {"first", "last"}:
        raise ValueError("occurrence must be 'first' or 'last'")
    if step.frame is None:
        return None
    rows = list(enumerate(step.frame.screen_after.visible_lines))
    if occurrence == "last":
        rows.reverse()
    for row, line in rows:
        if anchor in strip_control_sequences(line):
            return row
    return None


def _event_payload(event: PlaybackEvent) -> dict[str, Any]:
    payload = event.payload
    if isinstance(payload, TerminalSize):
        payload = {"columns": payload.columns, "rows": payload.rows}
    return {"kind": event.kind, "payload": payload}
