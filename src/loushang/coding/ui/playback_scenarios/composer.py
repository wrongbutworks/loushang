from __future__ import annotations

import asyncio

from loushang.coding.ui.completion import coding_inline_completion_provider
from loushang.coding.ui.playback import (
    NativeTuiInputPlaybackResult,
    NativeTuiInputScenario,
)
from loushang.coding.ui.playback_fakes import (
    SessionCommandPlaybackSession as _SessionCommandSession,
)
from loushang.coding.ui.playback_scenarios.budgets import INTERACTION_FRAME_BUDGET
from loushang.coding.ui.playback_suite import NativePlaybackScenarioSpec
from loushang.tui import PlaybackEvent, RenderConstraints
from loushang.tui.input import BRACKETED_PASTE_END, BRACKETED_PASTE_START


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


def _run_completion_session_command() -> NativeTuiInputPlaybackResult:
    session = _SessionCommandSession()
    scenario = NativeTuiInputScenario(width=80, height=12)
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


def _run_completion_navigation_priority() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_completion_escape_cancel() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_completion_prefix_refresh() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_completion_enter_submits_command() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_history_navigation() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_bracketed_paste_large_marker() -> NativeTuiInputPlaybackResult:
    pasted = "\n".join(f"line {index}" for index in range(10))
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_resize_reflow_stable() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_wide_char_input_cursor() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=32, height=10)
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


def _run_keyboard_shift_enter_newline() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_editor_key_editing() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_page_navigation() -> NativeTuiInputPlaybackResult:
    scenario = NativeTuiInputScenario(width=20, height=3).with_composer_text("one\ntwo\nthree\nfour\nfive")
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


def _run_paste_marker_delete_undo() -> NativeTuiInputPlaybackResult:
    pasted = "\n".join(f"line {index}" for index in range(10))
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _run_composer_selection_replace() -> NativeTuiInputPlaybackResult:
    result = (
        NativeTuiInputScenario(width=80, height=12)
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


def _result_from_scenario(scenario: NativeTuiInputScenario) -> NativeTuiInputPlaybackResult:
    playback = scenario.playback
    return NativeTuiInputPlaybackResult(
        steps=playback.harness.steps,
        port=playback.port,
        input_results=tuple(playback.input_results),
        step_input_results=tuple(playback.step_input_results),
        step_coding_states=tuple(playback.step_coding_states),
        app=scenario.app,
    )


COMPOSER_SCENARIOS = (
    NativePlaybackScenarioSpec(
        name="completion-tab",
        description="Apply tab completion without clearing or repainting the screen.",
        run=_run_completion_tab,
    ),
    NativePlaybackScenarioSpec(
        name="completion-session-command",
        description="Apply session command completion without executing the selected command.",
        run=_run_completion_session_command,
        tags=("completion", "command", "session"),
    ),
    NativePlaybackScenarioSpec(
        name="completion-navigation-priority",
        description="Route completion navigation before history navigation.",
        run=_run_completion_navigation_priority,
    ),
    NativePlaybackScenarioSpec(
        name="completion-escape-cancel",
        description="Cancel visible completions without clearing the composer draft.",
        run=_run_completion_escape_cancel,
        tags=("completion", "editor", "composer"),
    ),
    NativePlaybackScenarioSpec(
        name="completion-prefix-refresh",
        description="Refresh visible completions when the composer prefix changes.",
        run=_run_completion_prefix_refresh,
        tags=("completion", "editor", "composer"),
    ),
    NativePlaybackScenarioSpec(
        name="completion-enter-submits-command",
        description="Apply a selected slash command completion before local command submission.",
        run=_run_completion_enter_submits_command,
        tags=("completion", "command", "composer"),
    ),
    NativePlaybackScenarioSpec(
        name="history-navigation",
        description="Browse prompt history from a non-empty draft and restore the draft.",
        run=_run_history_navigation,
    ),
    NativePlaybackScenarioSpec(
        name="bracketed-paste-large-marker",
        description="Render a large bracketed paste as a stable composer marker.",
        run=_run_bracketed_paste_large_marker,
    ),
    NativePlaybackScenarioSpec(
        name="resize-reflow-stable",
        description="Keep composer text and cursor stable across terminal resizes.",
        run=_run_resize_reflow_stable,
    ),
    NativePlaybackScenarioSpec(
        name="wide-char-input-cursor",
        description="Keep CJK and emoji input cursor diagnostics aligned.",
        run=_run_wide_char_input_cursor,
    ),
    NativePlaybackScenarioSpec(
        name="keyboard-shift-enter-newline",
        description="Route raw Shift+Enter to composer newline before submission.",
        run=_run_keyboard_shift_enter_newline,
    ),
    NativePlaybackScenarioSpec(
        name="editor-key-editing",
        description="Route common editor keys for line movement, kill/yank, and undo.",
        run=_run_editor_key_editing,
        tags=("editor", "composer"),
    ),
    NativePlaybackScenarioSpec(
        name="page-navigation",
        description="Route composer PageUp and PageDown using playback terminal dimensions.",
        run=_run_page_navigation,
        tags=("editor", "composer"),
    ),
    NativePlaybackScenarioSpec(
        name="paste-marker-delete-undo",
        description="Delete a large paste marker atomically and restore it with undo.",
        run=_run_paste_marker_delete_undo,
        tags=("editor", "paste", "composer"),
    ),
    NativePlaybackScenarioSpec(
        name="composer-selection-replace",
        description="Extend composer selection with Shift+Left and replace it through typed input.",
        run=_run_composer_selection_replace,
        tags=("editor", "selection", "composer"),
    ),
)
