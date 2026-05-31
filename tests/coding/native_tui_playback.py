from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from io import StringIO

from loushang.coding.ui.native_app import NativeCodingTuiApp
from loushang.coding.ui.native_loop import run_native_coding_tui
from loushang.tui import (
    FakeTerminalPort,
    PlaybackStep,
    RenderLoop,
    TerminalOperation,
    TerminalSize,
    TuiRuntime,
    strip_control_sequences,
)

NativeTuiHandler = Callable[..., Awaitable[int | None] | int | None]
NativeTuiAbortHandler = Callable[[], Awaitable[object] | object]


@dataclass(slots=True)
class NativeTuiScenario:
    width: int = 80
    height: int = 24
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 0.0
    app: NativeCodingTuiApp = field(init=False)
    port: FakeTerminalPort = field(init=False)
    runtime: TuiRuntime = field(init=False)

    def __post_init__(self) -> None:
        self.app = NativeCodingTuiApp(
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

    def type_text(self, text: str) -> NativeTuiScenario:
        self.app.composer.set_text(text)
        return self

    def advance_time(self, seconds: float) -> NativeTuiScenario:
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


@dataclass(frozen=True, slots=True)
class NativeTuiLoopPlaybackResult:
    exit_code: int
    output: str
    app: NativeCodingTuiApp

    @property
    def text(self) -> str:
        return strip_control_sequences(self.output)


@dataclass(slots=True)
class NativeTuiLoopPlayback:
    width: int = 80
    height: int = 24
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 10.0
    app: NativeCodingTuiApp = field(init=False)

    def __post_init__(self) -> None:
        self.app = NativeCodingTuiApp(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
            now=lambda: self.now,
        )

    def run(
        self,
        *chunks: tuple[float, str],
        handle_prompt: NativeTuiHandler | None = None,
        handle_local: NativeTuiHandler | None = None,
        handle_steer: NativeTuiHandler | None = None,
        handle_followup: NativeTuiHandler | None = None,
        on_abort: NativeTuiAbortHandler | None = None,
        should_exit: Callable[[str], bool] | None = None,
        is_local_command: Callable[[str], bool] | None = None,
        terminal_mode_factory: Callable[..., object] | None = None,
    ) -> NativeTuiLoopPlaybackResult:
        stdout = StringIO()
        stdin = _TimedTtyChunkInput(*chunks) if chunks else StringIO("")
        exit_code = asyncio.run(
            run_native_coding_tui(
                app=self.app,
                stdin=stdin,
                stdout=stdout,
                handle_prompt=handle_prompt or (lambda _text: None),
                handle_local=handle_local,
                handle_steer=handle_steer,
                handle_followup=handle_followup,
                terminal_mode_factory=terminal_mode_factory or (lambda _stdin, _stdout: _NoTerminalMode()),
                on_abort=on_abort or (lambda: None),
                should_exit=should_exit or (lambda text: text in {"/quit", "/exit"}),
                is_local_command=is_local_command,
            )
        )
        return NativeTuiLoopPlaybackResult(exit_code=exit_code, output=stdout.getvalue(), app=self.app)


class _NoTerminalMode:
    def __enter__(self) -> "_NoTerminalMode":
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
