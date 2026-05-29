from __future__ import annotations

from loushang.coding.ui.tool_blocks import ToolTranscriptBlock
from loushang.tui.transcript import ToolExecutionRecord


def test_tool_block_projects_to_generic_tool_execution_record() -> None:
    from loushang.coding.ui.transcript_projection import tool_block_to_record

    block = ToolTranscriptBlock(
        tool_call_id="tc1",
        tool_name="bash",
        status="ok",
        verb="Ran",
        title="uv run pytest tests/tui -q",
        detail=None,
        body="passed\n2 passed",
    )

    record = tool_block_to_record(block, elapsed_seconds=1.25)

    assert record == ToolExecutionRecord(
        name="uv run pytest tests/tui -q",
        state="completed",
        elapsed_seconds=1.25,
        output="passed\n2 passed",
        command="uv run pytest tests/tui -q",
    )


def test_tool_block_projects_failure_detail_to_stderr_and_exit_code() -> None:
    from loushang.coding.ui.transcript_projection import tool_block_to_record

    block = ToolTranscriptBlock(
        tool_call_id="tc1",
        tool_name="bash",
        status="error",
        verb="Ran",
        title="pytest",
        detail="failed: exit code 2",
        body="",
    )

    record = tool_block_to_record(block, elapsed_seconds=0.5)

    assert record.state == "failed"
    assert record.stderr == "failed: exit code 2"
    assert record.exit_code == 2


def test_tool_block_infers_diff_output_kind() -> None:
    from loushang.coding.ui.transcript_projection import tool_block_to_record

    block = ToolTranscriptBlock(
        tool_call_id="tc1",
        tool_name="apply_patch",
        status="ok",
        verb="Edited",
        title="src/app.py",
        body="diff --git a/src/app.py b/src/app.py\n@@\n-old\n+new",
    )

    record = tool_block_to_record(block)

    assert record.output_kind == "diff"
    assert record.show_stats is True

