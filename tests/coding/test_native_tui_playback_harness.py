from __future__ import annotations

import asyncio

from native_tui_playback import NativeTuiLoopPlayback, NativeTuiScenario


def test_native_tui_scenario_renders_composer_input_without_screen_clear() -> None:
    scenario = NativeTuiScenario(width=80, height=18)
    scenario.render()

    step = scenario.type_text("hello").render()

    scenario.assert_operation_class(step, "changed_range_update")
    scenario.assert_no_clear(step)
    scenario.assert_visible_contains("› hello")
    scenario.assert_cursor_matches_diagnostics(step)


def test_native_tui_loop_playback_drives_running_steer_then_escape() -> None:
    playback = NativeTuiLoopPlayback()
    prompts: list[str] = []
    steers: list[tuple[str, str]] = []

    async def handle_prompt(text: str) -> None:
        prompts.append(text)
        if text == "change":
            playback.app.begin_assistant()
            playback.app.append_assistant_chunk("fresh change")
            return
        playback.app.begin_assistant()
        playback.app.append_assistant_chunk("working")
        await asyncio.Event().wait()

    async def handle_steer(text: str) -> None:
        steers.append(("queue" if playback.app.state.running else "execute", text))

    result = playback.run(
        (0.0, "go\r"),
        (0.01, "change\r"),
        (0.02, "\x1b"),
        (0.06, ""),
        handle_prompt=handle_prompt,
        handle_steer=handle_steer,
    )

    assert result.exit_code == 0
    assert prompts == ["go", "change"]
    assert steers == [("queue", "change")]
    assert "› go" in result.text
    assert "› change" in result.text
    assert "fresh change" in result.text
    assert "Conversation interrupted" in result.text
