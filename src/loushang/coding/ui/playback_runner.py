from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import TextIO

from loushang.coding.ui.perf_probe import build_synthetic_long_transcript_records
from loushang.coding.ui.playback import (
    NativeTuiInputPlaybackResult,
    NativeTuiInputScenario,
    NativeTuiLoopScenario,
)
from loushang.tui import PlaybackFrameBudget, SelectionSurface, SelectItem

INTERACTION_FRAME_BUDGET = PlaybackFrameBudget(
    disallowed_operation_classes=("baseline_repaint", "recovery_repaint"),
    max_operations=32,
    max_serialized_output_bytes=768,
    max_changed_visible_lines=8,
    require_synchronized=True,
)

LONG_TRANSCRIPT_FRAME_BUDGET = PlaybackFrameBudget(
    disallowed_operation_classes=("baseline_repaint", "recovery_repaint"),
    max_operations=12,
    max_serialized_output_bytes=2_000,
    max_changed_visible_lines=3,
    require_synchronized=True,
)


@dataclass(frozen=True, slots=True)
class NativePlaybackScenarioSpec:
    name: str
    description: str
    run: Callable[[], object]


@dataclass(frozen=True, slots=True)
class NativePlaybackScenarioResult:
    name: str
    ok: bool
    elapsed_ms: float
    artifacts: tuple[Path, ...] = ()
    error: str | None = None


class NativePlaybackSuite:
    def __init__(self, scenarios: Sequence[NativePlaybackScenarioSpec]) -> None:
        self._scenarios = tuple(scenarios)
        self._by_name = {scenario.name: scenario for scenario in self._scenarios}

    @property
    def scenarios(self) -> tuple[NativePlaybackScenarioSpec, ...]:
        return self._scenarios

    def names(self) -> tuple[str, ...]:
        return tuple(scenario.name for scenario in self._scenarios)

    def selected(self, names: Sequence[str]) -> tuple[NativePlaybackScenarioSpec, ...]:
        if not names:
            return self._scenarios
        return tuple(self.get(name) for name in names)

    def get(self, name: str) -> NativePlaybackScenarioSpec:
        try:
            return self._by_name[name]
        except KeyError as error:
            raise KeyError(name) from error


def run_playback_scenarios(
    names: Sequence[str] = (),
    *,
    suite: NativePlaybackSuite | None = None,
    artifacts_dir: str | Path | None = None,
    include_frames: bool = False,
) -> tuple[NativePlaybackScenarioResult, ...]:
    suite = DEFAULT_SUITE if suite is None else suite
    results: list[NativePlaybackScenarioResult] = []
    for scenario in suite.selected(tuple(names)):
        started = time.perf_counter()
        try:
            scenario_result = scenario.run()
            artifacts = _write_artifacts(
                scenario.name,
                scenario_result,
                artifacts_dir=artifacts_dir,
                include_frames=include_frames,
            )
            results.append(
                NativePlaybackScenarioResult(
                    name=scenario.name,
                    ok=True,
                    elapsed_ms=_elapsed_ms(started),
                    artifacts=artifacts,
                )
            )
        except AssertionError as error:
            artifacts = _write_error_artifact(scenario.name, error, artifacts_dir=artifacts_dir)
            results.append(
                NativePlaybackScenarioResult(
                    name=scenario.name,
                    ok=False,
                    elapsed_ms=_elapsed_ms(started),
                    artifacts=artifacts,
                    error=str(error),
                )
            )
    return tuple(results)


def run_playback_cli(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    suite: NativePlaybackSuite | None = None,
) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    suite = DEFAULT_SUITE if suite is None else suite
    parser = _build_parser()
    raw_argv = sys.argv[1:] if argv is None else tuple(argv)
    args = parser.parse_args(raw_argv)
    if args.list:
        _write_scenario_list(suite, stdout)
        return 0

    try:
        results = run_playback_scenarios(
            args.scenarios,
            suite=suite,
            artifacts_dir=args.artifacts,
            include_frames=args.include_frames,
        )
    except KeyError as error:
        stderr.write(f"Unknown scenario: {error.args[0]}\n")
        return 2

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        stdout.write(f"{status} {result.name} ({result.elapsed_ms:.1f}ms)\n")
        if result.error:
            stderr.write(f"{result.name}: {result.error}\n")
    return 0 if all(result.ok for result in results) else 1


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(run_playback_cli(argv))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m loushang.coding.ui.playback_runner",
        description="Run native TUI playback regression scenarios.",
    )
    parser.add_argument("scenarios", nargs="*", help="Scenario names to run. Defaults to all scenarios.")
    parser.add_argument("--list", action="store_true", help="List available scenarios.")
    parser.add_argument("--artifacts", help="Directory for manual inspection artifacts.")
    parser.add_argument("--include-frames", action="store_true", help="Include visible frames in JSONL artifacts.")
    return parser


def _write_scenario_list(suite: NativePlaybackSuite, stdout: TextIO) -> None:
    for scenario in suite.scenarios:
        stdout.write(f"{scenario.name}\t{scenario.description}\n")


def _run_completion_tab() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_completion_items("/model", "/models")
        .render()
        .type_text("/mod")
        .tab()
        .run()
    )
    result.assert_composer_text("/model ")
    result.assert_visible_contains("› /model")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_local_command() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_local_commands("/status")
        .render()
        .type_text("/status")
        .enter()
        .run()
    )
    result.assert_local_texts("/status")
    result.assert_prompt_texts()
    result.assert_composer_text("")
    result.assert_visible_not_contains("› /status")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_active_surface() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_active_surface(SelectionSurface([SelectItem("Choose me", value="chosen")]))
        .with_composer_text("draft")
        .render()
        .enter()
        .run()
    )
    result.assert_surface_intents(("select", "chosen"))
    result.assert_composer_text("draft")
    result.assert_visible_contains("Choose me")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_running_steer_queued() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_running_prompt("old")
        .render()
        .type_text("change")
        .enter()
        .run()
    )
    result.assert_steer_texts("change")
    result.assert_pending_steers("change")
    result.assert_composer_text("")
    result.assert_visible_contains("Messages to be submitted after next tool call")
    result.assert_visible_contains("change")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_running_escape_keeps_queued_steer() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_running_prompt("old")
        .with_pending_steers("queued")
        .render()
        .escape()
        .run()
    )
    result.assert_abort_requested()
    result.assert_pending_steers("queued")
    result.assert_visible_contains("Messages to be submitted after next tool call")
    result.assert_visible_contains("queued")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_idle_escape_pops_pending_steer() -> NativeTuiInputPlaybackResult:
    result = NativeTuiInputScenario(width=80, height=12).with_pending_steers("queued").render().escape().run()
    result.assert_steer_texts("queued")
    result.assert_pending_steers()
    result.assert_visible_not_contains("Messages to be submitted after next tool call")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_escape_pending_steer() -> object:
    scenario = NativeTuiLoopScenario()
    prompts: list[str] = []
    steers: list[str] = []

    async def handle_prompt(text: str) -> None:
        prompts.append(text)
        if text == "fresh":
            scenario.app.begin_assistant()
            scenario.app.append_assistant_chunk("fresh response")
            return
        scenario.app.begin_assistant()
        scenario.app.append_assistant_chunk("old response")
        await _never()

    async def handle_steer(text: str) -> None:
        steers.append(text)

    result = (
        scenario.type_text("old")
        .enter()
        .wait(0.01)
        .type_text("fresh")
        .enter()
        .wait(0.01)
        .escape()
        .wait(0.04)
        .end_input()
        .run(handle_prompt=handle_prompt, handle_steer=handle_steer)
    )
    result.assert_exit_code(0)
    result.assert_text_contains("› old")
    result.assert_text_contains("› fresh")
    result.assert_text_contains("fresh response")
    result.assert_text_not_contains("Request cancelled")
    result.assert_no_clear_screen()
    result.assert_idle()
    result.assert_pending_steers()
    result.assert_composer_text("")
    assert prompts == ["old", "fresh"]
    assert steers == ["fresh"]
    return result


def _run_escape_pending_steer_fifo() -> object:
    scenario = NativeTuiLoopScenario().with_pending_steers("prequeued")
    prompts: list[str] = []
    steers: list[str] = []

    async def handle_prompt(text: str) -> None:
        if text == "prequeued":
            prompts.append(text)
            return
        scenario.app.begin_assistant()
        scenario.app.append_assistant_chunk("working")
        await _never()

    async def handle_steer(text: str) -> None:
        steers.append(text)

    result = (
        scenario.type_text("start")
        .enter()
        .wait(0.01)
        .type_text("running steer")
        .enter()
        .wait(0.01)
        .escape()
        .wait(0.04)
        .end_input()
        .run(handle_prompt=handle_prompt, handle_steer=handle_steer)
    )
    result.assert_exit_code(0)
    assert steers == ["running steer"]
    assert prompts == ["prequeued"]
    result.assert_pending_steers("running steer")
    result.assert_no_clear_screen()
    return result


def _run_escape_pending_steer_preserves_draft() -> object:
    scenario = NativeTuiLoopScenario().with_pending_steers("queued")
    prompts: list[str] = []

    async def handle_prompt(text: str) -> None:
        if text == "queued":
            prompts.append(text)
            return
        await _never()

    result = (
        scenario.type_text("start")
        .enter()
        .wait(0.01)
        .type_text("draft")
        .wait(0.01)
        .escape()
        .wait(0.04)
        .end_input()
        .run(handle_prompt=handle_prompt)
    )
    result.assert_exit_code(0)
    assert prompts == ["queued"]
    result.assert_composer_text("draft")
    result.assert_pending_steers()
    result.assert_no_clear_screen()
    return result


def _run_running_follow_up_queued() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_running_prompt("old")
        .render()
        .type_text("follow")
        .key("\x1b\r")
        .run()
    )
    assert result.app.state.pending_followups == ["follow"]
    result.assert_pending_steers()
    result.assert_composer_text("")
    result.assert_visible_contains("queued=1 steer=0")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_long_transcript_input() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=100, height=18)
        .with_records(build_synthetic_long_transcript_records(turns=40, tail_tool_output_lines=300))
        .render()
        .type_chars("fresh input")
        .run()
    )
    result.assert_composer_text("fresh input")
    result.assert_visible_contains("› fresh input")
    result.assert_no_clear_screen()
    LONG_TRANSCRIPT_FRAME_BUDGET.assert_result(result, skip_first=True)
    result.assert_screen_anchor_stable("›", occurrence="last")
    return result


DEFAULT_SUITE = NativePlaybackSuite(
    (
        NativePlaybackScenarioSpec(
            name="completion-tab",
            description="Apply tab completion without clearing or repainting the screen.",
            run=_run_completion_tab,
        ),
        NativePlaybackScenarioSpec(
            name="local-command",
            description="Route a local command without echoing it as a prompt.",
            run=_run_local_command,
        ),
        NativePlaybackScenarioSpec(
            name="active-surface",
            description="Route enter to an active surface before the composer.",
            run=_run_active_surface,
        ),
        NativePlaybackScenarioSpec(
            name="running-steer-queued",
            description="Queue a submitted steer while a prompt is running.",
            run=_run_running_steer_queued,
        ),
        NativePlaybackScenarioSpec(
            name="running-escape-keeps-queued-steer",
            description="Abort a running prompt without dropping an existing queued steer.",
            run=_run_running_escape_keeps_queued_steer,
        ),
        NativePlaybackScenarioSpec(
            name="idle-escape-pops-pending-steer",
            description="Pop and execute the first pending steer when ESC is pressed while idle.",
            run=_run_idle_escape_pops_pending_steer,
        ),
        NativePlaybackScenarioSpec(
            name="escape-pending-steer",
            description="Exercise ESC with a queued steer through the native loop.",
            run=_run_escape_pending_steer,
        ),
        NativePlaybackScenarioSpec(
            name="escape-pending-steer-fifo",
            description="Preserve pending steer FIFO order when ESC interrupts a running prompt.",
            run=_run_escape_pending_steer_fifo,
        ),
        NativePlaybackScenarioSpec(
            name="escape-pending-steer-preserves-draft",
            description="Run an interrupt pending steer without clearing an unsubmitted composer draft.",
            run=_run_escape_pending_steer_preserves_draft,
        ),
        NativePlaybackScenarioSpec(
            name="running-follow-up-queued",
            description="Queue a follow-up while a prompt is running.",
            run=_run_running_follow_up_queued,
        ),
        NativePlaybackScenarioSpec(
            name="long-transcript-input",
            description="Echo input after a long transcript using bounded frame updates.",
            run=_run_long_transcript_input,
        ),
    )
)


async def _never() -> None:
    await asyncio.Event().wait()


def _write_artifacts(
    name: str,
    result: object,
    *,
    artifacts_dir: str | Path | None,
    include_frames: bool,
) -> tuple[Path, ...]:
    if artifacts_dir is None:
        return ()
    writer = getattr(result, "write_artifacts", None)
    if not callable(writer):
        return ()
    if "include_frames" in inspect.signature(writer).parameters:
        artifacts = writer(artifacts_dir, basename=name, include_frames=include_frames)
    else:
        artifacts = writer(artifacts_dir, basename=name)
    return tuple(Path(getattr(artifacts, field.name)) for field in fields(artifacts))


def _write_error_artifact(
    name: str,
    error: AssertionError,
    *,
    artifacts_dir: str | Path | None,
) -> tuple[Path, ...]:
    if artifacts_dir is None:
        return ()
    output_dir = Path(artifacts_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}-error.txt"
    path.write_text(f"{error}\n", encoding="utf-8")
    return (path,)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


if __name__ == "__main__":
    main()
