from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from loushang.coding.store.session_manager import SessionManager
from loushang.coding.ui.screen_app import ScreenCodingTuiApp
from loushang.coding.ui.session_history import session_history_records
from loushang.tui import RenderConstraints, RenderLoop, TerminalSize
from loushang.tui.transcript import (
    AssistantMessageRecord,
    DisplayRecord,
    ToolExecutionRecord,
    UserPromptRecord,
    WorkedDividerRecord,
)


@dataclass(frozen=True, slots=True)
class LongTranscriptRenderMetrics:
    visible_render_ms: float
    visible_render_line_count: int
    render_loop_plan_ms: float
    render_loop_logical_line_count: int
    render_loop_operation_class: str
    changed_line_range: tuple[int, int] | None


def build_synthetic_long_transcript_records(
    *,
    turns: int = 180,
    tail_tool_output_lines: int = 2400,
) -> tuple[DisplayRecord, ...]:
    records: list[DisplayRecord] = []
    for index in range(1, turns + 1):
        records.append(UserPromptRecord(f"Prompt {index}: inspect the current state."))
        records.append(
            AssistantMessageRecord(
                f"Assistant {index}: acknowledged. I will inspect the current state and report back."
            )
        )
        records.append(
            ToolExecutionRecord(
                name=f"read /repo/file_{index}.py",
                state="completed",
                elapsed_seconds=0.01,
                output=_tool_output_text(
                    index, tail_tool_output_lines if index == turns else 12
                ),
                command=f"read /repo/file_{index}.py",
            )
        )
        records.append(WorkedDividerRecord(0.25))
    return tuple(records)


def characterize_long_transcript_rendering(
    app: ScreenCodingTuiApp,
    *,
    width: int,
    height: int,
    composer_text: str = "",
    render_loop: RenderLoop | None = None,
    commit_plan: bool = False,
) -> LongTranscriptRenderMetrics:
    constraints = RenderConstraints(
        width=width, max_height=height, visible_height=height
    )
    if composer_text:
        app.composer.set_text(composer_text)

    visible_started = perf_counter()
    visible_result = app.render(constraints)
    visible_elapsed_ms = (perf_counter() - visible_started) * 1000

    active_render_loop = render_loop or RenderLoop(screen_root=app)
    plan_started = perf_counter()
    size = TerminalSize(columns=width, rows=height)
    diagnostics = active_render_loop.plan(size)
    plan_elapsed_ms = (perf_counter() - plan_started) * 1000
    if commit_plan:
        active_render_loop.commit(diagnostics, size=size)

    return LongTranscriptRenderMetrics(
        visible_render_ms=visible_elapsed_ms,
        visible_render_line_count=len(visible_result.lines),
        render_loop_plan_ms=plan_elapsed_ms,
        render_loop_logical_line_count=len(diagnostics.current_logical_lines),
        render_loop_operation_class=diagnostics.operation_class,
        changed_line_range=diagnostics.changed_line_range,
    )


async def load_session_history_records(
    session_file: str | Path,
    *,
    tool_definition_resolver: Any | None = None,
) -> tuple[DisplayRecord, ...]:
    manager = await SessionManager.load(Path(session_file).expanduser().resolve())
    session = _HistorySession(manager)
    return session_history_records(
        session, tool_definition_resolver=tool_definition_resolver
    )


class _HistorySession:
    def __init__(self, manager: SessionManager) -> None:
        self.session_manager = manager

    def get_session_context(self):
        return self.session_manager.build_session_context()


def _tool_output_text(index: int, lines: int) -> str:
    body = [
        f"{line_no:04d}: line {line_no} from synthetic tool output {index} with markdown `token-{line_no}`"
        for line_no in range(1, lines + 1)
    ]
    return "\n".join(body)
