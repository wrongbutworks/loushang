"""Coding compatibility adapter for shared tool transcript projection."""

from dataclasses import replace

from loushang.harnesstui.conversation.tool_transcript import (
    ToolTranscriptBlock,
)
from loushang.harnesstui.conversation.tool_transcript import (
    tool_block_to_record as project_neutral_tool_block,
)
from loushang.tui.transcript import ToolExecutionRecord


def tool_block_to_record(
    block: ToolTranscriptBlock, *, elapsed_seconds: float = 0.0
) -> ToolExecutionRecord:
    """Preserve Coding's legacy command-label policy at the product edge."""

    if block.command is None and block.verb in {"Ran", "Tested"}:
        block = replace(block, command=block.title)
    return project_neutral_tool_block(block, elapsed_seconds=elapsed_seconds)


__all__ = ["tool_block_to_record"]
