from __future__ import annotations

import asyncio

from loushang.coding.ui.completion import coding_inline_completion_provider
from loushang.coding.ui.playback import (
    ScreenTuiInputPlaybackResult,
    ScreenTuiInputScenario,
)
from loushang.coding.ui.playback_fakes import (
    SessionCommandPlaybackSession as _SessionCommandSession,
)
from loushang.coding.ui.playback_scenarios.budgets import INTERACTION_FRAME_BUDGET
from loushang.tui import (
    CompletionItem,
    CompletionProvider,
    PlaybackEvent,
    RenderConstraints,
)
from loushang.tui.input import BRACKETED_PASTE_END, BRACKETED_PASTE_START
from loushang.tui.playback_suite import (
    PlaybackScenarioSpec as ScreenPlaybackScenarioSpec,
)


def _run_completion_tab() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
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


def _run_completion_session_command() -> ScreenTuiInputPlaybackResult:
    session = _SessionCommandSession()
    scenario = ScreenTuiInputScenario(width=80, height=12)
    scenario.app.composer.set_completion_provider(asyncio.run(coding_inline_completion_provider(session)))

    result = scenario.render().type_text("/na").tab().run()

    result.assert_composer_text("/name ")
    result.assert_visible_contains("› /name")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    assert session.commands == []
    assert session.prompts == []
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_completion_navigation_priority() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .with_history("history prompt")
        .with_completion_items("/model", "/models")
        .render()
        .type_text("/mod")
        .key("\x1b[B")
        .tab()
        .run()
    )
    result.assert_composer_text("/models ")
    result.assert_visible_contains("› /models")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_completion_escape_cancel() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .with_completion_items("/help", "/history")
        .render()
        .type_text("/h")
        .escape()
        .run()
    )
    result.assert_composer_text("/h")
    result.assert_visible_contains("› /h")
    result.assert_visible_not_contains("  /help")
    result.assert_visible_not_contains("  /history")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_completion_prefix_refresh() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .with_completion_items("/help", "/history", "/model")
        .render()
        .type_text("/")
        .type_text("m")
        .run()
    )
    result.assert_composer_text("/m")
    result.assert_visible_contains("› /m")
    result.assert_visible_contains("  /model")
    result.assert_visible_not_contains("  /help")
    result.assert_visible_not_contains("  /history")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_completion_enter_submits_command() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .with_completion_items("/model", "/models")
        .with_local_commands("/model")
        .render()
        .type_text("/mod")
        .enter()
        .run()
    )
    result.assert_local_texts("/model")
    result.assert_composer_text("")
    result.assert_visible_not_contains("  /model")
    result.assert_visible_not_contains("  /models")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_history_navigation() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .with_history("first prompt", "second prompt")
        .render()
        .type_text("draft")
        .key("\x1b[A")
        .key("\x1b[A")
        .key("\x1b[B")
        .key("\x1b[B")
        .run()
    )
    assert [state["composer_text"] for state in result.step_coding_states[1:]] == [
        "draft",
        "second prompt",
        "first prompt",
        "second prompt",
        "draft",
    ]
    result.assert_composer_text("draft")
    result.assert_visible_contains("› draft")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_bracketed_paste_large_marker() -> ScreenTuiInputPlaybackResult:
    pasted = "\n".join(f"line {index}" for index in range(10))
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .key(f"{BRACKETED_PASTE_START}{pasted}{BRACKETED_PASTE_END}")
        .run()
    )
    result.assert_composer_text(pasted)
    result.assert_visible_contains("[paste #1 +10 lines]")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_resize_reflow_stable() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .type_text("resize keeps composer stable")
        .resize(width=42, height=8)
        .type_text(" after shrink")
        .resize(width=100, height=14)
        .type_text(" after grow")
        .run()
    )
    result.assert_composer_text("resize keeps composer stable after shrink after grow")
    result.assert_visible_contains("after grow")
    assert any(step.diagnostics.operation_class == "resize_repaint" for step in result.steps)
    result.assert_no_clear_scrollback()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_wide_char_input_cursor() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=32, height=10)
        .render()
        .type_chars("你好🙂 terminal")
        .run()
    )
    result.assert_composer_text("你好🙂 terminal")
    result.assert_visible_contains("你好🙂 terminal")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_keyboard_shift_enter_newline() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .type_text("first line")
        .key("\x1b[13;2u")
        .type_text("second line")
        .enter()
        .run()
    )
    result.assert_prompt_texts("first line\nsecond line")
    result.assert_composer_text("")
    result.assert_visible_contains("› first line")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_editor_key_editing() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .type_text("alpha beta gamma")
        .key("\x01say ")
        .key("\x05\x17")
        .key("\x19")
        .key("\x1f")
        .run()
    )
    result.assert_composer_text("say alpha beta ")
    result.assert_visible_contains("› say alpha beta")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_page_navigation() -> ScreenTuiInputPlaybackResult:
    scenario = ScreenTuiInputScenario(width=20, height=3).with_composer_text("one\ntwo\nthree\nfour\nfive")
    playback = scenario.playback

    playback.play((PlaybackEvent("render"), PlaybackEvent.input("\x1b[5~")))
    page_up = scenario.app.composer.render(RenderConstraints(width=20, max_height=5))
    assert page_up.cursor is not None
    assert (page_up.cursor.row, page_up.cursor.column) == (2, 6)

    playback.play((PlaybackEvent.input("\x1b[6~"),))
    page_down = scenario.app.composer.render(RenderConstraints(width=20, max_height=5))
    assert page_down.cursor is not None
    assert (page_down.cursor.row, page_down.cursor.column) == (4, 6)

    result = _result_from_scenario(scenario)
    result.assert_composer_text("one\ntwo\nthree\nfour\nfive")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_paste_marker_delete_undo() -> ScreenTuiInputPlaybackResult:
    pasted = "\n".join(f"line {index}" for index in range(10))
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .key(f"{BRACKETED_PASTE_START}{pasted}{BRACKETED_PASTE_END}")
        .key("\x7f")
        .key("\x1f")
        .run()
    )
    result.assert_composer_text(pasted)
    result.assert_visible_contains("[paste #1 +10 lines]")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_composer_selection_replace() -> ScreenTuiInputPlaybackResult:
    result = (
        ScreenTuiInputScenario(width=80, height=12)
        .render()
        .type_text("abc")
        .key("\x1b[1;2D")
        .type_text("x")
        .run()
    )
    selected_output = result.steps[2].frame.serialized_output if result.steps[2].frame else ""
    assert "\x1b[7mc\x1b[27m" in selected_output
    result.assert_composer_text("abx")
    result.assert_visible_contains("› abx")
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _run_composer_selection_stress() -> ScreenTuiInputPlaybackResult:
    scenario = ScreenTuiInputScenario(width=80, height=12)
    playback = scenario.playback

    playback.play(
        (
            PlaybackEvent("render"),
            PlaybackEvent.input("你🙂a"),
            PlaybackEvent.input("\x1b[1;2D"),
            PlaybackEvent.input("\x1b[1;2D"),
            PlaybackEvent.input("x"),
            PlaybackEvent.input("\x1b[1;2H"),
            PlaybackEvent.input("wide"),
            PlaybackEvent.input("\x1f"),
            PlaybackEvent.input("\x01"),
            PlaybackEvent.input("\x1b[1;2F"),
            PlaybackEvent.input("\x0b"),
            PlaybackEvent.input("\x19"),
            PlaybackEvent.input("\x1f"),
        )
    )
    assert scenario.app.composer.value == ""
    assert [state["composer_text"] for state in playback.step_coding_states[1:8]] == [
        "你🙂a",
        "你🙂a",
        "你🙂a",
        "你x",
        "你x",
        "wide",
        "你x",
    ]

    pasted = "\n".join(f"selected paste line {index}" for index in range(10))
    playback.play((PlaybackEvent.input(f"{BRACKETED_PASTE_START}{pasted}{BRACKETED_PASTE_END}"),))
    assert scenario.app.composer.value == pasted
    assert scenario.app.composer.selected_range is None
    assert "[paste #1 +10 lines]" in "\n".join(playback.port.screen.visible_lines)

    playback.play((PlaybackEvent.input("\x1b[1;2D"),))
    assert scenario.app.composer.selected_range == (0, 1)

    playback.play((PlaybackEvent.input("\x7f"),))
    assert scenario.app.composer.value == ""

    playback.play((PlaybackEvent.input("\x1f"),))
    assert scenario.app.composer.value == pasted
    assert "[paste #1 +10 lines]" in "\n".join(playback.port.screen.visible_lines)

    scenario.app.composer.clear()
    scenario.app.composer.set_completion_provider(
        CompletionProvider((CompletionItem(value="ax-alpha"), CompletionItem(value="ax-beta")))
    )
    playback.play(
        (
            PlaybackEvent.input("ab"),
            PlaybackEvent.input("\x1b[1;2D"),
            PlaybackEvent.input("x"),
        )
    )
    assert scenario.app.composer.value == "ax"
    assert scenario.app.composer.selected_range is None
    assert scenario.app.composer.has_completions
    assert "ax-alpha" in "\n".join(playback.port.screen.visible_lines)

    result = _result_from_scenario(scenario)
    result.assert_no_clear_screen()
    result.assert_cursor_matches_diagnostics()
    result.assert_any_frame_output_contains("\x1b[7m")
    INTERACTION_FRAME_BUDGET.assert_result(result, skip_first=True)
    return result


def _result_from_scenario(scenario: ScreenTuiInputScenario) -> ScreenTuiInputPlaybackResult:
    playback = scenario.playback
    return ScreenTuiInputPlaybackResult(
        steps=playback.harness.steps,
        port=playback.port,
        input_results=tuple(playback.input_results),
        step_input_results=tuple(playback.step_input_results),
        step_coding_states=tuple(playback.step_coding_states),
        app=scenario.app,
    )


COMPOSER_SCENARIOS = (
    ScreenPlaybackScenarioSpec(
        name="completion-tab",
        description="Apply tab completion without clearing or repainting the screen.",
        run=_run_completion_tab,
    ),
    ScreenPlaybackScenarioSpec(
        name="completion-session-command",
        description="Apply session command completion without executing the selected command.",
        run=_run_completion_session_command,
        tags=("completion", "command", "session"),
    ),
    ScreenPlaybackScenarioSpec(
        name="completion-navigation-priority",
        description="Route completion navigation before history navigation.",
        run=_run_completion_navigation_priority,
    ),
    ScreenPlaybackScenarioSpec(
        name="completion-escape-cancel",
        description="Cancel visible completions without clearing the composer draft.",
        run=_run_completion_escape_cancel,
        tags=("completion", "editor", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="completion-prefix-refresh",
        description="Refresh visible completions when the composer prefix changes.",
        run=_run_completion_prefix_refresh,
        tags=("completion", "editor", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="completion-enter-submits-command",
        description="Apply a selected slash command completion before local command submission.",
        run=_run_completion_enter_submits_command,
        tags=("completion", "command", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="history-navigation",
        description="Browse prompt history from a non-empty draft and restore the draft.",
        run=_run_history_navigation,
    ),
    ScreenPlaybackScenarioSpec(
        name="bracketed-paste-large-marker",
        description="Render a large bracketed paste as a stable composer marker.",
        run=_run_bracketed_paste_large_marker,
    ),
    ScreenPlaybackScenarioSpec(
        name="resize-reflow-stable",
        description="Keep composer text and cursor stable across terminal resizes.",
        run=_run_resize_reflow_stable,
    ),
    ScreenPlaybackScenarioSpec(
        name="wide-char-input-cursor",
        description="Keep CJK and emoji input cursor diagnostics aligned.",
        run=_run_wide_char_input_cursor,
    ),
    ScreenPlaybackScenarioSpec(
        name="keyboard-shift-enter-newline",
        description="Route raw Shift+Enter to composer newline before submission.",
        run=_run_keyboard_shift_enter_newline,
    ),
    ScreenPlaybackScenarioSpec(
        name="editor-key-editing",
        description="Route common editor keys for line movement, kill/yank, and undo.",
        run=_run_editor_key_editing,
        tags=("editor", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="page-navigation",
        description="Route composer PageUp and PageDown using playback terminal dimensions.",
        run=_run_page_navigation,
        tags=("editor", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="paste-marker-delete-undo",
        description="Delete a large paste marker atomically and restore it with undo.",
        run=_run_paste_marker_delete_undo,
        tags=("editor", "paste", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="composer-selection-replace",
        description="Extend composer selection with Shift+Left and replace it through typed input.",
        run=_run_composer_selection_replace,
        tags=("editor", "selection", "composer"),
    ),
    ScreenPlaybackScenarioSpec(
        name="composer-selection-stress",
        description="Stress composer selection across wide text, paste markers, kill/yank, undo, and completions.",
        run=_run_composer_selection_stress,
        tags=("editor", "selection", "paste", "completion", "composer"),
    ),
)
