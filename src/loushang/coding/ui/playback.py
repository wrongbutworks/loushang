from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import ScreenInputResult, ScreenInputRouter
from loushang.coding.ui.screen_loop import run_screen_coding_tui
from loushang.tui import (
    CompletionItem,
    CompletionProvider,
    FakeTerminalPort,
    InputReader,
    PlaybackEvent,
    PlaybackHarness,
    PlaybackResult,
    PlaybackScenario,
    PlaybackStep,
    RenderDiagnostics,
    RenderLoop,
    TerminalOperation,
    TerminalSize,
    TuiRuntime,
    playback_artifacts_directory_from_env,
    strip_control_sequences,
)
from loushang.tui.transcript import DisplayRecord

ScreenTuiHandler = Callable[..., Awaitable[int | None] | int | None]
ScreenTuiAbortHandler = Callable[[], Awaitable[object] | object]


@dataclass(frozen=True, slots=True)
class ScreenTuiLoopArtifacts:
    raw: Path
    text: Path
    state: Path


@dataclass(slots=True)
class ScreenTuiScenario:
    width: int = 80
    height: int = 24
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 0.0
    app: ScreenCodingTuiApp = field(init=False)
    port: FakeTerminalPort = field(init=False)
    runtime: TuiRuntime = field(init=False)

    def __post_init__(self) -> None:
        self.app = ScreenCodingTuiApp(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
            now=lambda: self.now,
        )
        self.port = FakeTerminalPort(size=TerminalSize(columns=self.width, rows=self.height))
        self.runtime = TuiRuntime(render_loop=RenderLoop(self.app), terminal=self.port)

    def render(self) -> PlaybackStep:
        return self.runtime.render_now()

    def type_text(self, text: str) -> ScreenTuiScenario:
        self.app.composer.set_text(text)
        return self

    def advance_time(self, seconds: float) -> ScreenTuiScenario:
        self.now += seconds
        return self

    def visible_text(self) -> str:
        return strip_control_sequences("\n".join(self.port.screen.visible_lines))

    def assert_visible_contains(self, text: str) -> None:
        assert text in self.visible_text()

    def assert_visible_not_contains(self, text: str) -> None:
        assert text not in self.visible_text()

    def assert_operation_class(self, step: PlaybackStep, expected: str) -> None:
        step.assert_operation_class(expected)

    def assert_no_clear(self, step: PlaybackStep) -> None:
        step.assert_no_clear_scrollback()
        assert TerminalOperation.clear_screen() not in step.diagnostics.operations

    def assert_cursor_matches_diagnostics(self, step: PlaybackStep) -> None:
        assert step.frame is not None
        assert step.frame.screen_after.cursor_row == step.diagnostics.hardware_cursor_row
        assert step.frame.screen_after.cursor_column == step.diagnostics.hardware_cursor_column


class ScreenTuiInputPlayback:
    def __init__(
        self,
        app: ScreenCodingTuiApp,
        *,
        columns: int = 80,
        rows: int = 12,
        should_exit: Callable[[str], bool] | None = None,
        is_local_command: Callable[[str], bool] | None = None,
    ) -> None:
        self.app = app
        self.reader = InputReader()
        self.input_results: list[ScreenInputResult] = []
        self.step_input_results: list[tuple[ScreenInputResult, ...]] = []
        self.step_coding_states: list[dict[str, Any]] = []
        self.router = ScreenInputRouter(
            app,
            should_exit=should_exit or (lambda _text: False),
            is_local_command=is_local_command or (lambda _text: False),
            width=columns,
            height=rows,
        )
        self.render_loop = RenderLoop(app, clear_scrollback_policy="disabled")
        port = FakeTerminalPort(size=TerminalSize(columns=columns, rows=rows))
        app.surface_host = TuiRuntime(render_loop=self.render_loop, terminal=port).overlay_host()
        self.harness = PlaybackHarness(
            render=self._render,
            port=port,
        )

    @property
    def port(self) -> FakeTerminalPort:
        return self.harness.port

    def play(self, events: list[PlaybackEvent] | tuple[PlaybackEvent, ...]) -> tuple[PlaybackStep, ...]:
        return self.harness.play(events)

    def _render(
        self,
        event: PlaybackEvent,
        size: TerminalSize,
        _previous: RenderDiagnostics | None,
    ) -> RenderDiagnostics:
        step_input_results: list[ScreenInputResult] = []
        if event.kind == "resize":
            self.router.width = size.columns
            self.router.height = size.rows
        elif event.kind == "input":
            if not isinstance(event.payload, str):
                raise TypeError("input playback event payload must be str")
            batch = self.reader.feed_batch(event.payload)
            input_events = list(batch.app_events)
            if self.reader.has_pending:
                input_events.extend(self.reader.flush_pending_batch().app_events)
            for input_event in input_events:
                result = self.router.handle(input_event)
                self.input_results.append(result)
                step_input_results.append(result)
        self.step_input_results.append(tuple(step_input_results))
        self.step_coding_states.append(_coding_state_payload(self.app))
        diagnostics = self.render_loop.plan(size)
        self.render_loop.commit(diagnostics, size=size)
        return diagnostics


@dataclass(frozen=True, slots=True)
class ScreenTuiInputPlaybackResult(PlaybackResult):
    input_results: tuple[ScreenInputResult, ...]
    step_input_results: tuple[tuple[ScreenInputResult, ...], ...]
    step_coding_states: tuple[dict[str, Any], ...]
    app: ScreenCodingTuiApp

    def assert_composer_text(self, expected: str) -> None:
        assert self.app.composer.value == expected

    def assert_prompt_texts(self, *expected: str) -> None:
        assert [result.prompt_text for result in self.input_results if result.prompt_text is not None] == list(expected)

    def assert_local_texts(self, *expected: str) -> None:
        assert [result.local_text for result in self.input_results if result.local_text is not None] == list(expected)

    def assert_surface_intents(self, *expected: tuple[str, str]) -> None:
        assert [
            (result.surface_intent.kind, result.surface_intent.text)
            for result in self.input_results
            if result.surface_intent is not None
        ] == list(expected)

    def assert_steer_texts(self, *expected: str) -> None:
        assert [result.steer_text for result in self.input_results if result.steer_text is not None] == list(expected)

    def assert_abort_requested(self) -> None:
        assert any(result.abort_requested for result in self.input_results)

    def assert_no_abort_requested(self) -> None:
        assert not any(result.abort_requested for result in self.input_results)

    def assert_pending_steers(self, *expected: str) -> None:
        assert self.app.state.pending_steers == list(expected)

    def _jsonl_row(self, step: PlaybackStep, *, include_frames: bool) -> dict[str, Any]:
        row = PlaybackResult._jsonl_row(self, step, include_frames=include_frames)
        step_input_results = self.step_input_results[step.index] if step.index < len(self.step_input_results) else ()
        coding_state = (
            self.step_coding_states[step.index]
            if step.index < len(self.step_coding_states)
            else _coding_state_payload(self.app)
        )
        row["coding"] = {
            **coding_state,
            "input_results": [_input_result_payload(result) for result in step_input_results],
        }
        return row


@dataclass(slots=True)
class ScreenTuiInputScenario(PlaybackScenario):
    width: int = 80
    height: int = 12
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 0.0
    app: ScreenCodingTuiApp = field(init=False)
    playback: ScreenTuiInputPlayback = field(init=False)

    def __post_init__(self) -> None:
        self.app = ScreenCodingTuiApp(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
            now=lambda: self.now,
        )
        self.playback = ScreenTuiInputPlayback(self.app, columns=self.width, rows=self.height)

    def with_running_prompt(self, text: str) -> ScreenTuiInputScenario:
        self.app.start_prompt(text, started_at=self.now)
        return self

    def with_pending_steers(self, *texts: str) -> ScreenTuiInputScenario:
        for text in texts:
            self.app.queue_steer(text)
        return self

    def with_history(self, *texts: str) -> ScreenTuiInputScenario:
        for text in texts:
            self.app.composer.add_history(text)
        return self

    def with_active_surface(self, surface: object) -> ScreenTuiInputScenario:
        self.app.active_surface = surface
        return self

    def with_composer_text(self, text: str) -> ScreenTuiInputScenario:
        self.app.composer.set_text(text)
        return self

    def with_records(self, records: tuple[DisplayRecord, ...] | list[DisplayRecord]) -> ScreenTuiInputScenario:
        self.app.state.records.extend(records)
        return self

    def with_completion_items(self, *values: str) -> ScreenTuiInputScenario:
        self.app.composer.set_completion_provider(
            CompletionProvider(tuple(CompletionItem(value=value) for value in values))
        )
        return self

    def with_local_commands(self, *commands: str) -> ScreenTuiInputScenario:
        command_set = set(commands)
        self.playback = ScreenTuiInputPlayback(
            self.app,
            columns=self.width,
            rows=self.height,
            is_local_command=lambda text: text in command_set,
        )
        return self

    def run(self) -> ScreenTuiInputPlaybackResult:
        return ScreenTuiInputPlaybackResult(
            steps=self.playback.play(self.events),
            port=self.playback.port,
            input_results=tuple(self.playback.input_results),
            step_input_results=tuple(self.playback.step_input_results),
            step_coding_states=tuple(self.playback.step_coding_states),
            app=self.app,
        )


@dataclass(frozen=True, slots=True)
class ScreenTuiLoopPlaybackResult:
    exit_code: int
    output: str
    app: ScreenCodingTuiApp

    @property
    def text(self) -> str:
        return strip_control_sequences(self.output)

    def assert_exit_code(self, expected: int) -> None:
        assert self.exit_code == expected

    def assert_text_contains(self, expected: str) -> None:
        assert expected in self.text

    def assert_text_not_contains(self, unexpected: str) -> None:
        assert unexpected not in self.text

    def assert_idle(self) -> None:
        assert self.app.state.running is False

    def assert_running(self) -> None:
        assert self.app.state.running is True

    def assert_pending_steers(self, *expected: str) -> None:
        assert self.app.state.pending_steers == list(expected)

    def assert_pending_followups(self, *expected: str) -> None:
        assert self.app.state.pending_followups == list(expected)

    def assert_composer_text(self, expected: str) -> None:
        assert self.app.composer.value == expected

    def assert_no_clear_screen(self) -> None:
        assert TerminalOperation.clear_screen().serialize() not in self.output
        assert TerminalOperation.clear_scrollback().serialize() not in self.output

    def write_artifacts(
        self,
        directory: str | Path,
        *,
        basename: str = "screen-loop",
    ) -> ScreenTuiLoopArtifacts:
        output_dir = Path(directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / f"{basename}-raw.txt"
        text_path = output_dir / f"{basename}-text.txt"
        state_path = output_dir / f"{basename}-state.json"
        raw_path.write_text(self.output, encoding="utf-8")
        text_path.write_text(self.text, encoding="utf-8")
        state_path.write_text(json.dumps(self._state_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        return ScreenTuiLoopArtifacts(raw=raw_path, text=text_path, state=state_path)

    @contextmanager
    def write_artifacts_on_failure(
        self,
        directory: str | Path,
        *,
        basename: str = "screen-loop",
    ) -> Iterator[None]:
        try:
            yield
        except Exception:
            self.write_artifacts(directory, basename=basename)
            raise

    @contextmanager
    def write_artifacts_on_failure_from_env(
        self,
        *,
        basename: str = "screen-loop",
        env: Mapping[str, str] | None = None,
    ) -> Iterator[None]:
        try:
            yield
        except Exception:
            if directory := playback_artifacts_directory_from_env(env):
                self.write_artifacts(directory, basename=basename)
            raise

    def _state_payload(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            **_coding_state_payload(self.app),
        }


@dataclass(slots=True)
class ScreenTuiLoopPlayback:
    width: int = 80
    height: int = 24
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 10.0
    app: ScreenCodingTuiApp = field(init=False)

    def __post_init__(self) -> None:
        self.app = ScreenCodingTuiApp(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
            now=lambda: self.now,
        )

    def run(
        self,
        *chunks: tuple[float, str],
        handle_prompt: ScreenTuiHandler | None = None,
        handle_local: ScreenTuiHandler | None = None,
        handle_steer: ScreenTuiHandler | None = None,
        handle_followup: ScreenTuiHandler | None = None,
        handle_surface_intent: ScreenTuiHandler | None = None,
        on_abort: ScreenTuiAbortHandler | None = None,
        should_exit: Callable[[str], bool] | None = None,
        is_local_command: Callable[[str], bool] | None = None,
        terminal_mode_factory: Callable[..., object] | None = None,
    ) -> ScreenTuiLoopPlaybackResult:
        stdout = StringIO()
        stdin = _TimedTtyChunkInput(*chunks) if chunks else StringIO("")
        exit_code = asyncio.run(
            run_screen_coding_tui(
                app=self.app,
                stdin=stdin,
                stdout=stdout,
                handle_prompt=handle_prompt or (lambda _text: None),
                handle_local=handle_local,
                handle_steer=handle_steer,
                handle_followup=handle_followup,
                handle_surface_intent=handle_surface_intent,
                terminal_mode_factory=terminal_mode_factory or (lambda _stdin, _stdout: _NoTerminalMode()),
                terminal_size_provider=lambda: TerminalSize(columns=self.width, rows=self.height),
                on_abort=on_abort or (lambda: None),
                should_exit=should_exit or (lambda text: text in {"/quit", "/exit"}),
                is_local_command=is_local_command,
            )
        )
        return ScreenTuiLoopPlaybackResult(exit_code=exit_code, output=stdout.getvalue(), app=self.app)


@dataclass(slots=True)
class ScreenTuiLoopScenario:
    """Script timed screen TUI input without repeating pipe/thread setup in tests."""

    playback: ScreenTuiLoopPlayback = field(default_factory=ScreenTuiLoopPlayback)
    _time: float = 0.0
    _chunks: list[tuple[float, str]] = field(default_factory=list)

    @property
    def app(self) -> ScreenCodingTuiApp:
        return self.playback.app

    def with_pending_steers(self, *texts: str) -> ScreenTuiLoopScenario:
        for text in texts:
            self.app.queue_steer(text)
        return self

    def with_composer_text(self, text: str) -> ScreenTuiLoopScenario:
        self.app.composer.set_text(text)
        return self

    def type_text(self, text: str) -> ScreenTuiLoopScenario:
        self._chunks.append((self._time, text))
        return self

    def type_chars(self, text: str) -> ScreenTuiLoopScenario:
        for character in text:
            self._chunks.append((self._time, character))
        return self

    def enter(self) -> ScreenTuiLoopScenario:
        return self.key("\r")

    def escape(self) -> ScreenTuiLoopScenario:
        return self.key("\x1b")

    def ctrl_c(self) -> ScreenTuiLoopScenario:
        return self.key("\x03")

    def key(self, raw: str) -> ScreenTuiLoopScenario:
        self._chunks.append((self._time, raw))
        return self

    def wait(self, seconds: float) -> ScreenTuiLoopScenario:
        self._time += max(0.0, seconds)
        return self

    def end_input(self) -> ScreenTuiLoopScenario:
        self._chunks.append((self._time, ""))
        return self

    def run(
        self,
        *,
        handle_prompt: ScreenTuiHandler | None = None,
        handle_local: ScreenTuiHandler | None = None,
        handle_steer: ScreenTuiHandler | None = None,
        handle_followup: ScreenTuiHandler | None = None,
        handle_surface_intent: ScreenTuiHandler | None = None,
        on_abort: ScreenTuiAbortHandler | None = None,
        should_exit: Callable[[str], bool] | None = None,
        is_local_command: Callable[[str], bool] | None = None,
    ) -> ScreenTuiLoopPlaybackResult:
        return self.playback.run(
            *self._chunks,
            handle_prompt=handle_prompt,
            handle_local=handle_local,
            handle_steer=handle_steer,
            handle_followup=handle_followup,
            handle_surface_intent=handle_surface_intent,
            on_abort=on_abort,
            should_exit=should_exit,
            is_local_command=is_local_command,
        )


class _NoTerminalMode:
    def __enter__(self) -> _NoTerminalMode:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


class _TimedTtyChunkInput:
    def __init__(self, *chunks: tuple[float, str], block_seconds: float = 0.002) -> None:
        self._start = time.perf_counter()
        self._block_seconds = block_seconds
        self._read_fd, write_fd = os.pipe()
        self._closed = threading.Event()

        def writer() -> None:
            try:
                for emit_at, chunk in chunks:
                    while (remaining := emit_at - (time.perf_counter() - self._start)) > 0:
                        time.sleep(min(self._block_seconds, remaining))
                    if self._closed.is_set():
                        break
                    os.write(write_fd, chunk.encode())
            finally:
                os.close(write_fd)

        self._writer = threading.Thread(target=writer, daemon=True)
        self._writer.start()

    def fileno(self) -> int:
        return self._read_fd

    def isatty(self) -> bool:
        return True

    def read(self, _size: int) -> str:
        return ""


def _input_result_payload(result: ScreenInputResult) -> dict[str, Any]:
    return {
        "prompt_text": result.prompt_text,
        "local_text": result.local_text,
        "steer_text": result.steer_text,
        "followup_text": result.followup_text,
        "surface_intent": _surface_intent_payload(result),
        "abort_requested": result.abort_requested,
        "exit_code": result.exit_code,
        "render_requested": result.render_requested,
    }


def _surface_intent_payload(result: ScreenInputResult) -> dict[str, str] | None:
    if result.surface_intent is None:
        return None
    return {"kind": result.surface_intent.kind, "text": result.surface_intent.text}


def _coding_state_payload(app: ScreenCodingTuiApp) -> dict[str, Any]:
    return {
        "composer_text": app.composer.value,
        "running": app.state.running,
        "pending_steers": list(app.state.pending_steers),
        "pending_followups": list(app.state.pending_followups),
    }
