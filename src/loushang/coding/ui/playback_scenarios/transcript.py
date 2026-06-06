from __future__ import annotations

from loushang.coding.ui.perf_probe import build_synthetic_long_transcript_records
from loushang.coding.ui.playback import (
    NativeTuiInputPlaybackResult,
    NativeTuiInputScenario,
)
from loushang.coding.ui.playback_scenarios.budgets import (
    INTERACTION_FRAME_BUDGET,
    LONG_TRANSCRIPT_FRAME_BUDGET,
)
from loushang.coding.ui.playback_suite import NativePlaybackScenarioSpec
from loushang.tui import strip_control_sequences
from loushang.tui.transcript import AssistantMessageRecord, ToolExecutionRecord


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


def _run_tool_output_preview() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=100, height=16)
        .with_records(
            (
                ToolExecutionRecord(
                    name="bash pytest tests/coding -q",
                    state="completed",
                    elapsed_seconds=0.6,
                    output="\n".join(f"line {index}" for index in range(1, 13)),
                ),
            )
        )
        .render()
        .type_text("next")
        .run()
    )
    result.assert_visible_contains("  └ line 1")
    result.assert_visible_contains("    line 3")
    result.assert_visible_contains("    ... (6 hidden lines)")
    result.assert_visible_contains("    line 12")
    result.assert_visible_not_contains("    line 4")
    result.assert_visible_not_contains("    line 9")
    result.assert_visible_contains("› next")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_transcript_reader_modal() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=72, height=8)
        .with_records(
            (
                AssistantMessageRecord(
                    "\n".join(f"answer line {index}" for index in range(12))
                ),
            )
        )
        .with_composer_text("draft")
        .with_completion_items("drafted")
        .render()
        .key("\x0f")
        .tab()
        .key("\x02")
        .key("\x06")
        .ctrl_c()
        .type_text("!")
        .run()
    )
    result.assert_composer_text("draft!")
    result.assert_prompt_texts()
    result.assert_local_texts()
    result.assert_no_abort_requested()
    result.assert_visible_contains("› draft!")
    result.assert_visible_not_contains("Ctrl+O/q/Esc close")
    result.assert_no_clear_screen()

    opened_screen = _step_screen(result, 1)
    tab_screen = _step_screen(result, 2)
    ctrl_b_screen = _step_screen(result, 3)
    ctrl_f_screen = _step_screen(result, 4)
    assert "Ctrl+O/q/Esc close" in opened_screen
    assert "PgUp/Ctrl+B · PgDn/Ctrl+F page" in opened_screen
    assert "answer line 11" in opened_screen
    assert "Ctrl+O/q/Esc close" in tab_screen
    assert result.step_coding_states[2]["composer_text"] == "draft"
    assert "answer line 4" in ctrl_b_screen
    assert "answer line 11" in ctrl_f_screen
    return result


def _step_screen(result: NativeTuiInputPlaybackResult, step_index: int) -> str:
    step = result.steps[step_index]
    assert step.frame is not None
    return strip_control_sequences("\n".join(step.frame.screen_after.visible_lines))


TRANSCRIPT_SCENARIOS = (
    NativePlaybackScenarioSpec(
        name="long-transcript-input",
        description="Echo input after a long transcript using bounded frame updates.",
        run=_run_long_transcript_input,
    ),
    NativePlaybackScenarioSpec(
        name="tool-output-preview",
        description="Render long tool output as head, hidden-count, and tail without flicker.",
        run=_run_tool_output_preview,
    ),
    NativePlaybackScenarioSpec(
        name="transcript-reader-modal",
        description="Open the transcript reader, keep input modal, close it, and resume composing.",
        run=_run_transcript_reader_modal,
    ),
)


__all__ = ["TRANSCRIPT_SCENARIOS"]
