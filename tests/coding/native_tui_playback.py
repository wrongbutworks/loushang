from __future__ import annotations

from dataclasses import dataclass, field

from loushang.coding.ui.native_app import NativeCodingTuiApp
from loushang.tui import (
    FakeTerminalPort,
    PlaybackStep,
    RenderLoop,
    TerminalOperation,
    TerminalSize,
    TuiRuntime,
    strip_control_sequences,
)


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
