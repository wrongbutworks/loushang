from __future__ import annotations

import json
from dataclasses import dataclass, field

from loushang.harnesstui.conversation.screen_state import ScreenConversationState
from loushang.harnesstui.testing.screen_loop_playback import (
    ConversationScreenLoopPlayback,
    ConversationScreenLoopScenario,
    ScriptedInputChunk,
)
from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.framework import SurfaceHost
from loushang.tui.terminal_capabilities import TerminalRuntimeCapabilities
from loushang.tui.ui_parts.composer import Composer


@dataclass(slots=True)
class _ScreenApp:
    clock: object
    composer: Composer = field(default_factory=Composer)
    state: ScreenConversationState = field(default_factory=ScreenConversationState)
    active_surface: object | None = None
    surface_host: SurfaceHost | None = None
    render_requester: object | None = None
    terminal_diagnostics_provider: object | None = None
    terminal_capabilities: TerminalRuntimeCapabilities | None = None
    errors: list[str] = field(default_factory=list)

    def now(self) -> float:
        assert callable(self.clock)
        return self.clock()

    def open_transcript_reader(self) -> bool:
        return False

    def start_prompt(self, text: str) -> None:
        self.state.start_prompt(text, started_at=self.now())
        self.composer.add_history(text)
        self.composer.clear()

    def start_pending_prompt(self, text: str) -> None:
        self.start_prompt(text)

    def queue_followup(self, text: str) -> None:
        self.state.queue_followup(text)

    def queue_steer(self, text: str) -> None:
        self.state.queue_steer(text)

    def add_error(self, summary: str, diagnostics: str = "") -> None:
        del diagnostics
        self.errors.append(summary)

    def complete_run(self, *, elapsed_seconds: float | None = None) -> None:
        self.state.complete_run(elapsed_seconds=elapsed_seconds or 0.0)

    def elapsed_seconds(self) -> float:
        return 0.0

    def startup_welcome_panel(self) -> _ScreenApp:
        return self

    def render(self, constraints: RenderConstraints) -> RenderResult:
        del constraints
        return RenderResult(lines=())


def _app_factory(*, now):
    return _ScreenApp(clock=now)


def test_screen_loop_playback_runs_scripted_chunks_through_shared_runner() -> None:
    prompts: list[str] = []
    playback = ConversationScreenLoopPlayback(
        app_factory=_app_factory,
        interruption_message="interrupted",
        cancellation_message="cancelled",
        width=40,
        height=8,
    )

    async def handle_prompt(text: str) -> None:
        prompts.append(text)

    result = playback.run(
        ScriptedInputChunk(0.0, "hello"),
        (0.0, "\r"),
        (0.01, ""),
        handle_prompt=handle_prompt,
    )

    result.assert_exit_code(0)
    result.assert_idle()
    result.assert_composer_text("")
    result.assert_no_clear_screen()
    assert prompts == ["hello"]
    assert result.state_snapshot["running"] is False


def test_screen_loop_scenario_builds_timed_input_recipe() -> None:
    prompts: list[str] = []
    scenario = ConversationScreenLoopScenario(
        playback=ConversationScreenLoopPlayback(
            app_factory=_app_factory,
            interruption_message="interrupted",
            cancellation_message="cancelled",
        )
    )

    async def handle_prompt(text: str) -> None:
        prompts.append(text)

    result = (
        scenario.type_chars("hi")
        .enter()
        .wait(0.01)
        .end_input()
        .run(handle_prompt=handle_prompt)
    )

    assert prompts == ["hi"]
    result.assert_exit_code(0)


def test_screen_loop_artifacts_separate_snapshot_and_result_payload(tmp_path) -> None:
    playback = ConversationScreenLoopPlayback(
        app_factory=_app_factory,
        interruption_message="interrupted",
        cancellation_message="cancelled",
        state_snapshot=lambda app: {"draft": app.composer.value},
        result_payload=lambda exit_code, _app: {"runner": {"exit": exit_code}},
    )

    result = playback.run()
    artifacts = result.write_artifacts(tmp_path, basename="loop")
    state = json.loads(artifacts.state.read_text(encoding="utf-8"))

    assert state == {
        "exit_code": 0,
        "conversation": {"draft": ""},
        "runner": {"exit": 0},
    }
