from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RawTextDelta:
    text: str


@dataclass(slots=True)
class RawDone:
    stop_reason: str = "stop"
    response_id: str | None = None
    usage: dict[str, int] | None = None


@dataclass(slots=True)
class RawError:
    message: str
    response_id: str | None = None
    usage: dict[str, int] | None = None
