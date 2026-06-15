from __future__ import annotations

import asyncio

from loushang.coding.ui.playback import (
    ScreenTuiInputPlaybackResult,
    ScreenTuiInputScenario,
    ScreenTuiLoopScenario,
)
from loushang.coding.ui.playback_scenarios.budgets import INTERACTION_FRAME_BUDGET
from loushang.coding.ui.playback_suite import ScreenPlaybackScenarioSpec


def _run_idle_escape_clears_draft() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .type_text("draft")
        .escape()
        .run()
    )
    result.assert_composer_text("")
    result.assert_no_abort_requested()
    result.assert_visible_not_contains("› draft")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_running_steer_queued() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
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


def _run_running_escape_keeps_queued_steer() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
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


def _run_idle_escape_pops_pending_steer() -> ScreenTuiInputPlaybackResult:
    result = ScreenTuiInputScenario(width=80, height=12).with_pending_steers("queued").render().escape().run()
    result.assert_steer_texts("queued")
    result.assert_pending_steers()
    result.assert_visible_not_contains("Messages to be submitted after next tool call")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_escape_pending_steer() -> object:
    scenario = ScreenTuiLoopScenario()
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
    scenario = ScreenTuiLoopScenario().with_pending_steers("prequeued")
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
    scenario = ScreenTuiLoopScenario().with_pending_steers("queued")
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


def _run_screen_loop_ctrl_c_abort_running() -> object:
    scenario = ScreenTuiLoopScenario()
    prompts: list[str] = []
    aborts: list[str] = []

    async def handle_prompt(text: str) -> None:
        prompts.append(text)
        scenario.app.begin_assistant()
        scenario.app.append_assistant_chunk("working before ctrl-c")
        await _never()

    async def on_abort() -> None:
        aborts.append("abort")

    result = (
        scenario.type_text("long running")
        .enter()
        .wait(0.01)
        .ctrl_c()
        .wait(0.04)
        .end_input()
        .run(handle_prompt=handle_prompt, on_abort=on_abort)
    )
    result.assert_exit_code(0)
    assert prompts == ["long running"]
    assert aborts == ["abort"]
    result.assert_idle()
    result.assert_text_contains("› long running")
    result.assert_text_contains("Conversation interrupted")
    result.assert_no_clear_screen()
    return result


def _run_running_follow_up_queued() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
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


def _run_keyboard_alt_enter_follow_up() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .with_running_prompt("active")
        .render()
        .type_text("follow-up through raw alt enter")
        .key("\x1b\r")
        .run()
    )
    assert result.app.state.pending_followups == ["follow-up through raw alt enter"]
    result.assert_pending_steers()
    result.assert_composer_text("")
    result.assert_visible_contains("queued=1 steer=0")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


LIFECYCLE_SCENARIOS = (
    ScreenPlaybackScenarioSpec(
        name="idle-escape-clears-draft",
        description="Clear an idle composer draft with ESC without aborting a run.",
        run=_run_idle_escape_clears_draft,
    ),
    ScreenPlaybackScenarioSpec(
        name="running-steer-queued",
        description="Queue a submitted steer while a prompt is running.",
        run=_run_running_steer_queued,
    ),
    ScreenPlaybackScenarioSpec(
        name="running-escape-keeps-queued-steer",
        description="Abort a running prompt without dropping an existing queued steer.",
        run=_run_running_escape_keeps_queued_steer,
    ),
    ScreenPlaybackScenarioSpec(
        name="idle-escape-pops-pending-steer",
        description="Pop and execute the first pending steer when ESC is pressed while idle.",
        run=_run_idle_escape_pops_pending_steer,
    ),
    ScreenPlaybackScenarioSpec(
        name="escape-pending-steer",
        description="Exercise ESC with a queued steer through the screen loop.",
        run=_run_escape_pending_steer,
    ),
    ScreenPlaybackScenarioSpec(
        name="escape-pending-steer-fifo",
        description="Preserve pending steer FIFO order when ESC interrupts a running prompt.",
        run=_run_escape_pending_steer_fifo,
    ),
    ScreenPlaybackScenarioSpec(
        name="escape-pending-steer-preserves-draft",
        description="Run an interrupt pending steer without clearing an unsubmitted composer draft.",
        run=_run_escape_pending_steer_preserves_draft,
    ),
    ScreenPlaybackScenarioSpec(
        name="screen-loop-ctrl-c-abort-running",
        description="Abort a running screen loop prompt via raw Ctrl-C without clearing the screen.",
        run=_run_screen_loop_ctrl_c_abort_running,
    ),
    ScreenPlaybackScenarioSpec(
        name="running-follow-up-queued",
        description="Queue a follow-up while a prompt is running.",
        run=_run_running_follow_up_queued,
    ),
    ScreenPlaybackScenarioSpec(
        name="keyboard-alt-enter-follow-up",
        description="Route raw Alt+Enter to follow-up submission while running.",
        run=_run_keyboard_alt_enter_follow_up,
    ),
)


async def _never() -> None:
    await asyncio.Event().wait()
