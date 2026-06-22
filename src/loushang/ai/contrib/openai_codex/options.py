from __future__ import annotations

from dataclasses import dataclass

from loushang.ai.options import CallOptions, Transport


@dataclass(frozen=True, slots=True)
class OpenAICodexResponsesOptions(CallOptions):
    """OpenAI Codex contrib request options."""

    on_payload: object | None = None
    on_response: object | None = None
    reasoning: str | None = None
    reasoning_summary: str | None = None
    text_verbosity: str | None = None
    transport: Transport | None = None
    session_id: str | None = None


__all__ = ["OpenAICodexResponsesOptions"]
