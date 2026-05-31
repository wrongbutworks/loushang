from __future__ import annotations

import asyncio

from native_tui_playback import (
    NativeTuiInputScenario,
    NativeTuiLoopScenario,
    NativeTuiScenario,
)


def test_native_tui_scenario_renders_composer_input_without_screen_clear() -> None:
    scenario = NativeTuiScenario(width=80, height=18)
    scenario.render()

    step = scenario.type_text("hello").render()

    scenario.assert_operation_class(step, "changed_range_update")
    scenario.assert_no_clear(step)
    scenario.assert_visible_contains("› hello")
    scenario.assert_cursor_matches_diagnostics(step)


def test_native_tui_input_scenario_scripts_input_without_screen_clear() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .type_text("hello")
        .type_text(" world")
        .run()
    )

    result.assert_all_flush_succeeded()
    result.assert_visible_contains("› hello world")
    result.assert_composer_text("hello world")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()


def test_native_tui_input_scenario_scripts_resize_without_scrollback_or_cursor_drift() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .type_text("hello")
        .resize(width=42, height=8)
        .type_text(" world")
        .run()
    )

    result.assert_all_flush_succeeded()
    result.assert_visible_contains("› hello world")
    result.assert_composer_text("hello world")
    result.assert_no_clear_scrollback()
    result.assert_cursor_matches_diagnostics()


def test_native_tui_input_scenario_captures_prompt_submission_without_screen_clear() -> None:
    result = NativeTuiInputScenario(width=80, height=12).type_text("hello").enter().run()

    result.assert_prompt_texts("hello")
    result.assert_composer_text("")
    result.assert_visible_contains("› hello")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()


def test_native_tui_input_scenario_captures_running_steer_without_screen_clear() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_running_prompt("old")
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


def test_native_tui_input_scenario_escape_abort_does_not_pop_pending_steer() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_running_prompt("old")
        .with_pending_steers("queued")
        .escape()
        .run()
    )

    result.assert_abort_requested()
    result.assert_pending_steers("queued")
    result.assert_visible_contains("Messages to be submitted after next tool call")
    result.assert_visible_contains("queued")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()


def test_native_tui_input_scenario_idle_escape_pops_pending_steer() -> None:
    result = NativeTuiInputScenario(width=80, height=12).with_pending_steers("queued").escape().run()

    result.assert_steer_texts("queued")
    result.assert_pending_steers()
    result.assert_visible_not_contains("Messages to be submitted after next tool call")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()


def test_native_tui_loop_playback_drives_running_steer_then_escape() -> None:
    scenario = NativeTuiLoopScenario()
    prompts: list[str] = []
    steers: list[tuple[str, str]] = []

    async def handle_prompt(text: str) -> None:
        prompts.append(text)
        if text == "change":
            scenario.app.begin_assistant()
            scenario.app.append_assistant_chunk("fresh change")
            return
        scenario.app.begin_assistant()
        scenario.app.append_assistant_chunk("working")
        await asyncio.Event().wait()

    async def handle_steer(text: str) -> None:
        steers.append(("queue" if scenario.app.state.running else "execute", text))

    result = (
        scenario.type_text("go")
        .enter()
        .wait(0.01)
        .type_text("change")
        .enter()
        .wait(0.01)
        .escape()
        .wait(0.04)
        .end_input()
        .run(handle_prompt=handle_prompt, handle_steer=handle_steer)
    )

    result.assert_exit_code(0)
    assert prompts == ["go", "change"]
    assert steers == [("queue", "change")]
    result.assert_text_contains("› go")
    result.assert_text_contains("› change")
    result.assert_text_contains("fresh change")
    result.assert_text_contains("Conversation interrupted")
    result.assert_no_clear_screen()


def test_native_tui_loop_scenario_drives_escape_pending_steer_flow() -> None:
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
        await asyncio.Event().wait()

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


def test_native_tui_loop_scenario_keeps_pending_steer_fifo_on_escape() -> None:
    scenario = NativeTuiLoopScenario().with_pending_steers("prequeued")
    prompts: list[str] = []
    steers: list[str] = []

    async def handle_prompt(text: str) -> None:
        if text == "prequeued":
            prompts.append(text)
            return
        scenario.app.begin_assistant()
        scenario.app.append_assistant_chunk("working")
        await asyncio.Event().wait()

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


def test_native_tui_loop_scenario_preserves_composer_draft_when_escape_runs_pending_steer() -> None:
    scenario = NativeTuiLoopScenario().with_pending_steers("queued")
    prompts: list[str] = []

    async def handle_prompt(text: str) -> None:
        if text == "queued":
            prompts.append(text)
            return
        await asyncio.Event().wait()

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
