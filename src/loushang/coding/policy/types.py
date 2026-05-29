from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PolicyDecision:
    disposition: Literal["allow", "deny", "ask"]
    reason: str | None = None
    code: str | None = None

    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls(disposition="allow")

    @classmethod
    def deny(cls, reason: str, *, code: str | None = None) -> "PolicyDecision":
        return cls(disposition="deny", reason=reason, code=code)

    @classmethod
    def ask(cls, reason: str, *, code: str | None = None) -> "PolicyDecision":
        return cls(disposition="ask", reason=reason, code=code)
