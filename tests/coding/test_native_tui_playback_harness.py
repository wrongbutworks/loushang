from __future__ import annotations

from native_tui_playback import NativeTuiScenario


def test_native_tui_scenario_renders_composer_input_without_screen_clear() -> None:
    scenario = NativeTuiScenario(width=80, height=18)
    scenario.render()

    step = scenario.type_text("hello").render()

    scenario.assert_operation_class(step, "changed_range_update")
    scenario.assert_no_clear(step)
    scenario.assert_visible_contains("› hello")
    scenario.assert_cursor_matches_diagnostics(step)
