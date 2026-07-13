from typing import Literal, NotRequired, TypedDict

from loushang.harness.presentation import ToolRenderContext, ToolRenderResultOptions
from loushang.harness.tools.core import (
    ToolDefinition,
    ToolRenderCall,
    ToolRenderOutput,
    ToolRenderResult,
)


class ToolTruncationDetails(TypedDict, total=False):
    content: str
    truncated: bool
    truncatedBy: NotRequired[Literal["lines", "bytes"] | None]
    totalLines: int
    outputLines: int
    maxLines: int
    totalBytes: int
    outputBytes: int
    maxBytes: int
    firstLineExceedsLimit: bool
    lastLinePartial: bool


# Accepted compatibility name for the existing tool-result wire shape.
PiTruncationDetails = ToolTruncationDetails

__all__ = [
    "PiTruncationDetails",
    "ToolDefinition",
    "ToolRenderCall",
    "ToolRenderContext",
    "ToolRenderOutput",
    "ToolRenderResult",
    "ToolRenderResultOptions",
    "ToolTruncationDetails",
]
