from __future__ import annotations


def test_coding_tool_transcript_projection_preserves_compatibility_aliases() -> None:
    from loushang.coding.presentation.tui.tool_transcript import (
        ToolCallSnapshot as CodingToolCallSnapshot,
    )
    from loushang.coding.presentation.tui.tool_transcript import (
        ToolTranscriptBlock as CodingToolTranscriptBlock,
    )
    from loushang.coding.presentation.tui.tool_transcript import (
        ToolTranscriptStatus as CodingToolTranscriptStatus,
    )
    from loushang.coding.presentation.tui.tool_transcript import (
        tool_block_to_record as coding_tool_block_to_record,
    )
    from loushang.harnesstui.conversation.tool_transcript import (
        ToolCallSnapshot,
        ToolTranscriptBlock,
        ToolTranscriptStatus,
    )

    assert CodingToolCallSnapshot is ToolCallSnapshot
    assert CodingToolTranscriptBlock is ToolTranscriptBlock
    assert CodingToolTranscriptStatus is ToolTranscriptStatus

    legacy_block = CodingToolTranscriptBlock(
        tool_call_id="tc1",
        tool_name="bash",
        status="ok",
        verb="Ran",
        title="pytest -q",
    )
    assert coding_tool_block_to_record(legacy_block).command == "pytest -q"
