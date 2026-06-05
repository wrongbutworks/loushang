from __future__ import annotations

from loushang.coding.ui.perf_probe import build_synthetic_long_transcript_records
from loushang.coding.ui.playback import (
    NativeTuiInputPlaybackResult,
    NativeTuiInputScenario,
)
from loushang.coding.ui.playback_suite import NativePlaybackScenarioSpec
from loushang.tui import (
    PlaybackEvent,
    PlaybackFrameBudget,
    SettingItem,
    SettingsSurface,
    strip_control_sequences,
)

PRODUCT_COMPOSED_FRAME_BUDGET = PlaybackFrameBudget(
    disallowed_operation_classes=("baseline_repaint", "recovery_repaint"),
    max_operations=64,
    max_serialized_output_bytes=3_000,
    max_changed_visible_lines=20,
    require_synchronized=True,
)


def _run_product_composed_interaction() -> NativeTuiInputPlaybackResult:
    scenario = (
        NativeTuiInputScenario(width=100, height=18)
        .with_records(
            build_synthetic_long_transcript_records(
                turns=24, tail_tool_output_lines=120
            )
        )
        .with_running_prompt("investigate product playback")
        .with_completion_items("/model", "/models")
    )

    scenario.playback.play(
        (
            PlaybackEvent("render"),
            PlaybackEvent.input("follow one"),
            PlaybackEvent.input("\x1b\r"),
        )
    )
    assert scenario.app.state.pending_followups == ["follow one"]
    _assert_visible_contains(scenario, "Queued follow-up inputs")
    _assert_visible_contains(scenario, "follow one")

    scenario.app.active_surface = SettingsSurface(
        (
            SettingItem(id="memory", label="Memory", current_value="on"),
            SettingItem(id="model", label="Model", current_value="kimi"),
        ),
        enable_search=True,
    )
    scenario.playback.play(
        (
            PlaybackEvent("render"),
            PlaybackEvent.input("mo\x1b[Dx"),
        )
    )
    _assert_visible_contains(scenario, "Search: mxo")
    _assert_visible_contains(scenario, "No matching settings")

    scenario.app.active_surface = None
    scenario.playback.play(
        (
            PlaybackEvent("render"),
            PlaybackEvent.input("/mod"),
            PlaybackEvent.input("\t"),
            PlaybackEvent.input("gpt"),
            PlaybackEvent.input("\x1b[1;2D"),
            PlaybackEvent.input("x"),
        )
    )

    result = _result_from_scenario(scenario)
    assert result.app.state.pending_followups == ["follow one"]
    result.assert_composer_text("/model gpx")
    result.assert_visible_contains("› /model gpx")
    result.assert_visible_contains("queued=1 steer=0")
    result.assert_no_clear_screen()
    PRODUCT_COMPOSED_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _result_from_scenario(
    scenario: NativeTuiInputScenario,
) -> NativeTuiInputPlaybackResult:
    return NativeTuiInputPlaybackResult(
        steps=scenario.playback.harness.steps,
        port=scenario.playback.port,
        input_results=tuple(scenario.playback.input_results),
        step_input_results=tuple(scenario.playback.step_input_results),
        step_coding_states=tuple(scenario.playback.step_coding_states),
        app=scenario.app,
    )


def _assert_visible_contains(scenario: NativeTuiInputScenario, expected: str) -> None:
    visible = strip_control_sequences(
        "\n".join(scenario.playback.port.screen.visible_lines)
    )
    assert expected in visible


PRODUCT_SCENARIOS = (
    NativePlaybackScenarioSpec(
        name="product-composed-interaction",
        description="Exercise long transcript, running queue, settings search, completion, and selection in one playback.",
        run=_run_product_composed_interaction,
        tags=(
            "product",
            "transcript",
            "lifecycle",
            "surface",
            "completion",
            "selection",
        ),
    ),
)


__all__ = ["PRODUCT_SCENARIOS"]
