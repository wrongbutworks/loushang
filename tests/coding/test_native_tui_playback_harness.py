from __future__ import annotations

import asyncio
import json

from loushang.coding.ui.perf_probe import build_synthetic_long_transcript_records
from loushang.coding.ui.playback import (
    NativeTuiInputScenario,
    NativeTuiLoopScenario,
    NativeTuiScenario,
)
from loushang.tui import SelectionSurface, SelectItem


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


def test_native_tui_input_scenario_writes_coding_jsonl_for_manual_inspection(tmp_path) -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_running_prompt("old")
        .type_text("change")
        .enter()
        .run()
    )
    path = tmp_path / "native-playback.jsonl"

    result.write_jsonl(path)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["coding"]["composer_text"] == "change"
    assert rows[0]["coding"]["pending_steers"] == []
    assert rows[-1]["coding"] == {
        "composer_text": "",
        "running": True,
        "pending_steers": ["change"],
        "pending_followups": [],
        "input_results": [
            {
                "prompt_text": None,
                "local_text": None,
                "steer_text": "change",
                "followup_text": None,
                "surface_intent": None,
                "abort_requested": False,
                "exit_code": None,
                "render_requested": True,
            }
        ],
    }


def test_native_tui_input_scenario_applies_tab_completion_without_screen_clear() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_completion_items("/model", "/models")
        .type_text("/mod")
        .tab()
        .run()
    )

    result.assert_composer_text("/model ")
    result.assert_visible_contains("› /model")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()


def test_native_tui_input_scenario_captures_local_command_without_prompt_echo() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_local_commands("/status")
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


def test_native_tui_input_scenario_routes_active_surface_before_composer() -> None:
    result = (
        NativeTuiInputScenario(width=80, height=12)
        .with_active_surface(SelectionSurface([SelectItem("Choose me", value="chosen")]))
        .with_composer_text("draft")
        .enter()
        .run()
    )

    result.assert_surface_intents(("select", "chosen"))
    result.assert_composer_text("draft")
    result.assert_visible_contains("Choose me")
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


def test_native_tui_input_scenario_echoes_input_after_long_transcript_without_repaint() -> None:
    result = (
        NativeTuiInputScenario(width=100, height=18)
        .with_records(build_synthetic_long_transcript_records(turns=40, tail_tool_output_lines=300))
        .render()
        .type_text("fresh input")
        .run()
    )

    result.assert_composer_text("fresh input")
    result.assert_visible_contains("› fresh input")
    result.assert_no_clear_screen()
    result.assert_operation_classes_not_in("baseline_repaint", "recovery_repaint", skip_first=True)
    result.assert_max_operations_per_step(12, skip_first=True)
    result.assert_screen_anchor_stable("›", occurrence="last")
    result.assert_synchronized_frames()


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
