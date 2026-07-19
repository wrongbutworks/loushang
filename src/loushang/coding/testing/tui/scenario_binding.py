from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO, cast

from loushang.coding.testing.tui.scenarios.budgets import (
    INTERACTION_FRAME_BUDGET,
    LONG_TRANSCRIPT_FRAME_BUDGET,
)
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.screen_input import build_screen_input_router
from loushang.coding.ui.screen_loop import run_screen_coding_tui
from loushang.harnesstui.conversation.screen_runner import (
    AbortHandler,
    ConversationInputResultPort,
    ConversationInputRouterFactoryPort,
    ConversationScreenPort,
    LocalCommandPredicate,
    PromptHandler,
    ShouldExit,
    SurfaceIntentHandler,
    TerminalModeFactory,
    TerminalSizeProvider,
    TextHandler,
)
from loushang.harnesstui.testing.input_playback import (
    ConversationInputPlayback,
    ConversationInputPlaybackResult,
)
from loushang.harnesstui.testing.ports import (
    ConversationPlaybackAppPort,
    ConversationPlaybackInputRouterPort,
)
from loushang.harnesstui.testing.scenarios.factory import (
    ConversationScenarioFactory,
    ScenarioFrameContracts,
)
from loushang.harnesstui.testing.screen_loop_playback import (
    ConversationScreenLoopPlayback,
    ConversationScreenLoopPlaybackResult,
    ScriptedInputChunk,
)
from loushang.tui.keybindings import KeybindingConfig, KeybindingManager
from loushang.tui.playback import PlaybackResult, PlaybackStep

CODING_INTERRUPTION_MESSAGE = (
    "Conversation interrupted - tell the model what to do differently."
)
CODING_CANCELLATION_MESSAGE = "Operation aborted"


def coding_scenario_input_router_factory(
    *,
    app: ConversationPlaybackAppPort,
    should_exit: ShouldExit,
    is_local_command: LocalCommandPredicate,
    keybindings: KeybindingManager | KeybindingConfig | None,
    width: int,
    height: int,
) -> ConversationPlaybackInputRouterPort[ConversationInputResultPort]:
    """Build the real Coding input adapter behind the neutral testing port."""

    return cast(
        ConversationPlaybackInputRouterPort[ConversationInputResultPort],
        build_screen_input_router(
            app=cast(ScreenCodingTuiApp, app),
            should_exit=should_exit,
            is_local_command=is_local_command,
            keybindings=keybindings,
            width=width,
            height=height,
        ),
    )


async def run_coding_scenario_screen_loop(
    *,
    app: ConversationScreenPort,
    stdin: TextIO,
    stdout: TextIO,
    handle_prompt: PromptHandler,
    handle_local: TextHandler | None,
    handle_steer: TextHandler | None,
    handle_followup: TextHandler | None,
    handle_surface_intent: SurfaceIntentHandler | None,
    on_abort: AbortHandler,
    should_exit: ShouldExit,
    is_local_command: LocalCommandPredicate | None,
    terminal_mode_factory: TerminalModeFactory | None,
    terminal_size_provider: TerminalSizeProvider,
    interruption_message: str,
    cancellation_message: str,
    input_router_factory: ConversationInputRouterFactoryPort | None,
) -> int:
    """Run recipes through Coding's production screen-loop adapter."""

    if interruption_message != CODING_INTERRUPTION_MESSAGE:
        raise ValueError(
            "Coding scenario interruption copy does not match the product adapter"
        )
    if cancellation_message != CODING_CANCELLATION_MESSAGE:
        raise ValueError(
            "Coding scenario cancellation copy does not match the product adapter"
        )
    del input_router_factory
    return await run_screen_coding_tui(
        app=cast(ScreenCodingTuiApp, app),
        stdin=stdin,
        stdout=stdout,
        handle_prompt=handle_prompt,
        handle_local=handle_local,
        handle_steer=handle_steer,
        handle_followup=handle_followup,
        handle_surface_intent=handle_surface_intent,
        on_abort=on_abort,
        should_exit=should_exit,
        is_local_command=is_local_command,
        terminal_mode_factory=terminal_mode_factory,
        terminal_size_provider=terminal_size_provider,
    )


@dataclass(frozen=True, slots=True)
class CodingScenarioInputPlaybackResult(
    ConversationInputPlaybackResult[ScreenCodingTuiApp]
):
    @property
    def step_coding_states(self) -> tuple[dict[str, object], ...]:
        """Compatibility spelling retained in Coding playback artifacts."""

        return self.step_state_snapshots

    def _jsonl_row(
        self,
        step: PlaybackStep,
        *,
        include_frames: bool,
    ) -> dict[str, Any]:
        row = PlaybackResult._jsonl_row(self, step, include_frames=include_frames)
        step_results = (
            self.step_input_results[step.index]
            if step.index < len(self.step_input_results)
            else ()
        )
        state = (
            self.step_state_snapshots[step.index]
            if step.index < len(self.step_state_snapshots)
            else _coding_state_snapshot(self.app)
        )
        row["coding"] = {
            **state,
            "input_results": [
                _coding_input_result_payload(result) for result in step_results
            ],
        }
        return row


class CodingScenarioInputPlayback(ConversationInputPlayback[ScreenCodingTuiApp]):
    def result(self) -> CodingScenarioInputPlaybackResult:
        return CodingScenarioInputPlaybackResult(
            steps=self.harness.steps,
            port=self.port,
            input_results=tuple(self.input_results),
            step_input_results=tuple(self.step_input_results),
            step_state_snapshots=tuple(self.step_state_snapshots),
            app=self.app,
            result_payload=self._result_payload,
        )


@dataclass(frozen=True, slots=True)
class CodingScenarioScreenLoopPlaybackResult(
    ConversationScreenLoopPlaybackResult[ScreenCodingTuiApp]
):
    def _artifact_payload(self) -> dict[str, object]:
        return {"exit_code": self.exit_code, **self.state_snapshot}


class CodingScenarioScreenLoopPlayback(
    ConversationScreenLoopPlayback[ScreenCodingTuiApp]
):
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
    ) -> CodingScenarioScreenLoopPlaybackResult:
        result = super().run(
            *chunks,
            handle_prompt=handle_prompt,
            handle_local=handle_local,
            handle_steer=handle_steer,
            handle_followup=handle_followup,
            handle_surface_intent=handle_surface_intent,
            on_abort=on_abort,
            should_exit=should_exit,
            is_local_command=is_local_command,
            terminal_mode_factory=terminal_mode_factory,
        )
        return CodingScenarioScreenLoopPlaybackResult(
            exit_code=result.exit_code,
            output=result.output,
            app=result.app,
            state_snapshot=result.state_snapshot,
            result_payload=result.result_payload,
        )


class _CodingConversationScenarioFactory(
    ConversationScenarioFactory[ScreenCodingTuiApp]
):
    def _build_input_playback(
        self,
        app: ScreenCodingTuiApp,
        *,
        columns: int,
        rows: int,
        should_exit: ShouldExit | None,
        is_local_command: LocalCommandPredicate | None,
        keybindings: KeybindingManager | KeybindingConfig | None,
    ) -> ConversationInputPlayback[ScreenCodingTuiApp]:
        return CodingScenarioInputPlayback(
            app,
            columns=columns,
            rows=rows,
            should_exit=should_exit,
            is_local_command=is_local_command,
            keybindings=keybindings,
            input_router_factory=self.input_router_factory,
            state_snapshot=self.state_snapshot,
            result_payload=self.input_result_payload,
        )

    def _build_screen_loop_playback(
        self,
        *,
        width: int,
        height: int,
        now: float,
    ) -> ConversationScreenLoopPlayback[ScreenCodingTuiApp]:
        return CodingScenarioScreenLoopPlayback(
            app_factory=self.app_factory,
            interruption_message=self.interruption_message,
            cancellation_message=self.cancellation_message,
            width=width,
            height=height,
            now=now,
            runner=self.screen_loop_runner,
            input_router_factory=cast(
                ConversationInputRouterFactoryPort,
                self.input_router_factory,
            ),
            state_snapshot=self.state_snapshot,
            result_payload=self.loop_result_payload,
        )


def _coding_app_factory(*, now: Callable[[], float]) -> ScreenCodingTuiApp:
    return ScreenCodingTuiApp(
        model_label="kimi",
        cwd="/repo",
        branch="main",
        session_label="abcd",
        now=now,
    )


def _coding_state_snapshot(app: ScreenCodingTuiApp) -> dict[str, object]:
    return {
        "composer_text": app.composer.value,
        "running": app.state.running,
        "pending_steers": list(app.state.pending_steers),
        "pending_followups": list(app.state.pending_followups),
    }


def _coding_input_result_payload(
    result: ConversationInputResultPort,
) -> dict[str, object]:
    intent = result.surface_intent
    return {
        "prompt_text": result.prompt_text,
        "local_text": result.local_text,
        "steer_text": result.steer_text,
        "followup_text": result.followup_text,
        "surface_intent": (
            None if intent is None else {"kind": intent.kind, "text": intent.text}
        ),
        "abort_requested": result.abort_requested,
        "exit_code": result.exit_code,
        "render_requested": result.render_requested,
    }


CODING_SCENARIO_FACTORY = _CodingConversationScenarioFactory(
    app_factory=_coding_app_factory,
    input_router_factory=coding_scenario_input_router_factory,
    screen_loop_runner=run_coding_scenario_screen_loop,
    interruption_message=CODING_INTERRUPTION_MESSAGE,
    cancellation_message=CODING_CANCELLATION_MESSAGE,
    state_snapshot=_coding_state_snapshot,
    input_result_payload=_coding_input_result_payload,
)

CODING_SCENARIO_FRAME_CONTRACTS = ScenarioFrameContracts(
    interaction=INTERACTION_FRAME_BUDGET,
    long_transcript=LONG_TRANSCRIPT_FRAME_BUDGET,
)


__all__ = [
    "CODING_CANCELLATION_MESSAGE",
    "CODING_INTERRUPTION_MESSAGE",
    "CODING_SCENARIO_FACTORY",
    "CODING_SCENARIO_FRAME_CONTRACTS",
    "CodingScenarioInputPlayback",
    "CodingScenarioInputPlaybackResult",
    "CodingScenarioScreenLoopPlayback",
    "CodingScenarioScreenLoopPlaybackResult",
    "coding_scenario_input_router_factory",
    "run_coding_scenario_screen_loop",
]
