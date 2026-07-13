from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

PolicyDisposition = Literal["allow", "deny", "ask"]


@dataclass(frozen=True)
class PolicyDecision:
    """Product-neutral result from an injected policy evaluator."""

    disposition: PolicyDisposition
    reason: str | None = None
    code: str | None = None

    @classmethod
    def allow(cls) -> PolicyDecision:
        return cls(disposition="allow")

    @classmethod
    def deny(cls, reason: str, *, code: str | None = None) -> PolicyDecision:
        return cls(disposition="deny", reason=reason, code=code)

    @classmethod
    def ask(cls, reason: str, *, code: str | None = None) -> PolicyDecision:
        return cls(disposition="ask", reason=reason, code=code)


class PolicyEvaluator(Protocol):
    def evaluate(self, subject: str, /) -> PolicyDecision: ...
