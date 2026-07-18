from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from loushang.coding.testing.tui.scenario_binding import (
    CODING_CANCELLATION_MESSAGE,
    CODING_INTERRUPTION_MESSAGE,
    CODING_SCENARIO_FACTORY,
    CodingScenarioInputPlayback,
    CodingScenarioInputPlaybackResult,
    CodingScenarioScreenLoopPlayback,
    CodingScenarioScreenLoopPlaybackResult,
    coding_scenario_input_router_factory,
    run_coding_scenario_screen_loop,
)
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.harnesstui.conversation.screen_runner import (
    AbortHandler,
    ConversationInputResultPort,
    ConversationInputRouterFactoryPort,
    LocalCommandPredicate,
    PromptHandler,
    ShouldExit,
    SurfaceIntentHandler,
    TerminalModeFactory,
    TextHandler,
)
from loushang.harnesstui.testing.input_playback import ConversationInputScenario
from loushang.harnesstui.testing.ports import ConversationResultPayloadPort
from loushang.harnesstui.testing.screen_loop_playback import (
    ConversationScreenLoopArtifacts,
    ConversationScreenLoopScenario,
    ScriptedInputChunk,
)
from loushang.tui import (
    FakeTerminalPort,
    PlaybackEvent,
    PlaybackStep,
    RenderLoop,
    TerminalOperation,
    TerminalSize,
    TuiRuntime,
    strip_control_sequences,
)
from loushang.tui.transcript import DisplayRecord

ScreenTuiHandler = PromptHandler
ScreenTuiAbortHandler = AbortHandler


@dataclass(frozen=True, slots=True)
class ScreenTuiLoopArtifacts(ConversationScreenLoopArtifacts):
    """Coding-compatible artifact paths returned by loop playback."""


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
        self.app = _screen_app(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
            now=lambda: self.now,
        )
        self.port = FakeTerminalPort(
            size=TerminalSize(columns=self.width, rows=self.height)
        )
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
        assert (
            step.frame.screen_after.cursor_row == step.diagnostics.hardware_cursor_row
        )
        assert (
            step.frame.screen_after.cursor_column
            == step.diagnostics.hardware_cursor_column
        )


class ScreenTuiInputPlayback(CodingScenarioInputPlayback):
    def __init__(
        self,
        app: ScreenCodingTuiApp,
        *,
        columns: int = 80,
        rows: int = 12,
        should_exit: ShouldExit | None = None,
        is_local_command: LocalCommandPredicate | None = None,
    ) -> None:
        super().__init__(
            app,
            columns=columns,
            rows=rows,
            should_exit=should_exit,
            is_local_command=is_local_command,
            input_router_factory=coding_scenario_input_router_factory,
            state_snapshot=_coding_state_payload,
            result_payload=_CODING_RESULT_PAYLOAD,
        )

    @property
    def step_coding_states(self) -> list[dict[str, object]]:
        return self.step_state_snapshots

    def result(self) -> ScreenTuiInputPlaybackResult:
        return ScreenTuiInputPlaybackResult(
            steps=self.harness.steps,
            port=self.port,
            input_results=tuple(self.input_results),
            step_input_results=tuple(self.step_input_results),
            step_coding_states=tuple(self.step_state_snapshots),
            app=self.app,
        )

    def run(self, events: Iterable[PlaybackEvent]) -> ScreenTuiInputPlaybackResult:
        self.play(events)
        return self.result()


class ScreenTuiInputPlaybackResult(CodingScenarioInputPlaybackResult):
    __slots__ = ()

    def __init__(
        self,
        steps: tuple[PlaybackStep, ...],
        port: FakeTerminalPort,
        input_results: tuple[ConversationInputResultPort, ...],
        step_input_results: tuple[tuple[ConversationInputResultPort, ...], ...],
        step_coding_states: tuple[dict[str, object], ...],
        app: ScreenCodingTuiApp,
    ) -> None:
        super().__init__(
            steps=steps,
            port=port,
            input_results=input_results,
            step_input_results=step_input_results,
            step_state_snapshots=step_coding_states,
            app=app,
            result_payload=_CODING_RESULT_PAYLOAD,
        )


@dataclass(slots=True)
class ScreenTuiInputScenario(ConversationInputScenario[ScreenCodingTuiApp]):
    playback: ScreenTuiInputPlayback = field(init=False)
    width: int = 80
    height: int = 12
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 0.0

    def __post_init__(self) -> None:
        app = _screen_app(
            model_label=self.model_label,
            cwd=self.cwd,
            branch=self.branch,
            session_label=self.session_label,
            now=lambda: self.now,
        )
        self.playback = ScreenTuiInputPlayback(
            app, columns=self.width, rows=self.height
        )

    def with_running_prompt(self, text: str) -> ScreenTuiInputScenario:
        self.app.start_prompt(text, started_at=self.now)
        return self

    def with_records(self, records: Iterable[DisplayRecord]) -> ScreenTuiInputScenario:
        self.app.state.records.extend(records)
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
        return self.playback.run(self.events)


class ScreenTuiLoopPlaybackResult(CodingScenarioScreenLoopPlaybackResult):
    __slots__ = ()

    def __init__(self, exit_code: int, output: str, app: ScreenCodingTuiApp) -> None:
        super().__init__(
            exit_code=exit_code,
            output=output,
            app=app,
            state_snapshot=_coding_state_payload(app),
        )

    def write_artifacts(
        self, directory: str | Path, *, basename: str = "screen-loop"
    ) -> ScreenTuiLoopArtifacts:
        artifacts = super().write_artifacts(directory, basename=basename)
        return ScreenTuiLoopArtifacts(
            raw=artifacts.raw,
            text=artifacts.text,
            state=artifacts.state,
        )

    @contextmanager
    def write_artifacts_on_failure(
        self, directory: str | Path, *, basename: str = "screen-loop"
    ) -> Iterator[None]:
        with super().write_artifacts_on_failure(directory, basename=basename):
            yield

    @contextmanager
    def write_artifacts_on_failure_from_env(
        self,
        *,
        basename: str = "screen-loop",
        env: Mapping[str, str] | None = None,
    ) -> Iterator[None]:
        with super().write_artifacts_on_failure_from_env(basename=basename, env=env):
            yield


@dataclass(slots=True, init=False)
class ScreenTuiLoopPlayback(CodingScenarioScreenLoopPlayback):
    width: int = 80
    height: int = 24
    model_label: str = "kimi"
    cwd: str = "/repo"
    branch: str | None = "main"
    session_label: str = "abcd"
    now: float = 10.0
    app: ScreenCodingTuiApp = field(init=False)

    def __init__(
        self,
        width: int = 80,
        height: int = 24,
        model_label: str = "kimi",
        cwd: str = "/repo",
        branch: str | None = "main",
        session_label: str = "abcd",
        now: float = 10.0,
    ) -> None:
        self.model_label = model_label
        self.cwd = cwd
        self.branch = branch
        self.session_label = session_label

        def app_factory(*, now: Callable[[], float]) -> ScreenCodingTuiApp:
            return _screen_app(
                model_label=self.model_label,
                cwd=self.cwd,
                branch=self.branch,
                session_label=self.session_label,
                now=now,
            )

        super().__init__(
            app_factory=app_factory,
            interruption_message=CODING_INTERRUPTION_MESSAGE,
            cancellation_message=CODING_CANCELLATION_MESSAGE,
            width=width,
            height=height,
            now=now,
            runner=run_coding_scenario_screen_loop,
            input_router_factory=cast(
                ConversationInputRouterFactoryPort,
                coding_scenario_input_router_factory,
            ),
            state_snapshot=_coding_state_payload,
        )

    def run(
        self,
        *chunks: ScriptedInputChunk | tuple[float, str],
        handle_prompt: PromptHandler | None = None,
        handle_local: TextHandler | None = None,
        handle_steer: TextHandler | None = None,
        handle_followup: TextHandler | None = None,
        handle_surface_intent: SurfaceIntentHandler | None = None,
        on_abort: AbortHandler | None = None,
        should_exit: ShouldExit | None = None,
        is_local_command: LocalCommandPredicate | None = None,
        terminal_mode_factory: TerminalModeFactory | None = None,
    ) -> ScreenTuiLoopPlaybackResult:
        result = super().run(
            *chunks,
            handle_prompt=handle_prompt,
            handle_local=handle_local,
            handle_steer=handle_steer,
            handle_followup=handle_followup,
            handle_surface_intent=handle_surface_intent,
            on_abort=on_abort,
            should_exit=should_exit or _should_exit,
            is_local_command=is_local_command,
            terminal_mode_factory=terminal_mode_factory,
        )
        return ScreenTuiLoopPlaybackResult(
            exit_code=result.exit_code, output=result.output, app=result.app
        )


@dataclass(slots=True)
class ScreenTuiLoopScenario(ConversationScreenLoopScenario[ScreenCodingTuiApp]):
    playback: ScreenTuiLoopPlayback = field(default_factory=ScreenTuiLoopPlayback)


def _screen_app(
    *,
    model_label: str,
    cwd: str,
    branch: str | None,
    session_label: str,
    now: Callable[[], float],
) -> ScreenCodingTuiApp:
    return ScreenCodingTuiApp(
        model_label=model_label,
        cwd=cwd,
        branch=branch,
        session_label=session_label,
        now=now,
    )


def _coding_state_payload(app: ScreenCodingTuiApp) -> dict[str, object]:
    return {
        "composer_text": app.composer.value,
        "running": app.state.running,
        "pending_steers": list(app.state.pending_steers),
        "pending_followups": list(app.state.pending_followups),
    }


def _should_exit(text: str) -> bool:
    return text in {"/quit", "/exit"}


_CODING_RESULT_PAYLOAD = cast(
    ConversationResultPayloadPort,
    CODING_SCENARIO_FACTORY.input_result_payload,
)
