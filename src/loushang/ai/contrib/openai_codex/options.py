from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loushang.ai.options import CallOptions, ReasoningOptions

CodexTransport = Literal["sse", "websocket", "auto"]


@dataclass(frozen=True, slots=True)
class OpenAICodexResponsesOptions(CallOptions):
    """OpenAI Codex contrib request options."""

    reasoning: ReasoningOptions | str | None = None  # type: ignore[assignment]
    reasoning_summary: str | None = None
    text_verbosity: str | None = None
    transport: CodexTransport | None = None
    session_id: str | None = None


__all__ = ["CodexTransport", "OpenAICodexResponsesOptions"]
