from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from loushang.ai.options import CallOptions

CodexTransport = Literal["sse", "websocket", "auto"]


@dataclass(frozen=True, slots=True)
class OpenAICodexResponsesOptions(CallOptions):
    """OpenAI Codex contrib request options."""

    text_verbosity: str | None = None
    transport: CodexTransport | None = None


__all__ = ["CodexTransport", "OpenAICodexResponsesOptions"]
