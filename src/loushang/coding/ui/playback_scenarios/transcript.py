from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

from loushang.coding.ui.controller import CodingUiController
from loushang.coding.ui.mode import _native_prompt_handler
from loushang.coding.ui.perf_probe import build_synthetic_long_transcript_records
from loushang.coding.ui.playback import (
    NativeTuiInputPlaybackResult,
    NativeTuiInputScenario,
    NativeTuiLoopPlayback,
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


def _run_transcript_reader_copy_command() -> object:
    playback = NativeTuiLoopPlayback(width=72, height=9)
    playback.app.state.records.extend(
        (
            AssistantMessageRecord("reader-visible latest answer"),
            AssistantMessageRecord("reader-visible older answer"),
        )
    )
    session = _CopyCommandPlaybackSession(
        recent_texts=(
            "latest structured answer",
            "previous structured answer",
        )
    )
    controller = CodingUiController(session=session)

    result = playback.run(
        (0.00, "\x0f"),
        (0.01, "\x02"),
        (0.02, "\x0f"),
        (0.03, "/copy 2\r"),
        (0.05, ""),
        handle_prompt=_native_prompt_handler(
            app=playback.app,
            controller=controller,
            stderr=StringIO(),
            verbose=False,
        ),
    )

    result.assert_exit_code(0)
    result.assert_text_contains("Transcript window")
    result.assert_text_contains("Ctrl+O/q/Esc close")
    result.assert_text_contains("Copied /copy 2 from structured source.")
    result.assert_no_clear_screen()
    assert session.commands == [("copy", "2")]
    assert session.prompts == []
    assert session.copied == ["previous structured answer"]
    return result


def _step_screen(result: NativeTuiInputPlaybackResult, step_index: int) -> str:
    step = result.steps[step_index]
    assert step.frame is not None
    return strip_control_sequences("\n".join(step.frame.screen_after.visible_lines))


class _CopyCommandPlaybackSession:
    def __init__(self, *, recent_texts: tuple[str, ...]) -> None:
        self.recent_texts = recent_texts
        self.commands: list[tuple[str, str]] = []
        self.prompts: list[str] = []
        self.copied: list[str] = []

    def list_commands(self) -> list[object]:
        return [
            SimpleNamespace(
                name="copy",
                description="Copy an assistant message to clipboard",
                source="builtin",
                argument_hint="[N]",
            )
        ]

    async def execute_command_async(self, invocation_name: str, args: str) -> object:
        self.commands.append((invocation_name, args))
        copy_index = int(args.strip() or "1")
        text = self.recent_texts[copy_index - 1]
        self.copied.append(text)
        return SimpleNamespace(
            invocation_name=invocation_name,
            result={
                "source": "builtin",
                "command": invocation_name,
                "status": "ok",
                "message": f"Copied /copy {copy_index} from structured source.",
                "index": copy_index,
                "characters": len(text),
            },
        )

    async def prompt(self, text: str, **_kwargs: object) -> None:
        self.prompts.append(text)


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
    NativePlaybackScenarioSpec(
        name="transcript-reader-copy-command",
        description="Open and close the transcript reader, then copy the second assistant response from structured history.",
        run=_run_transcript_reader_copy_command,
        tags=("transcript", "command"),
    ),
)


__all__ = ["TRANSCRIPT_SCENARIOS"]
