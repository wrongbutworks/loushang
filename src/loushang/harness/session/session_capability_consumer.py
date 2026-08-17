"""Focused Consumer for the side-question facet of ``harness.session``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast

from loushang.harness.capabilities.graph_runtime import CapabilityFacetSet
from loushang.harness.capabilities.session_contracts import (
    SESSION_SIDE_QUESTION_REQUIREMENT,
    SIDE_QUESTION_FACET,
)
from loushang.harness.runtime.side_question import (
    SideQuestionAnswer,
    SideQuestionUpdate,
)


class _SideQuestionFacet(Protocol):
    async def ask(
        self,
        question: str,
        *,
        on_update: SideQuestionUpdate | None = None,
    ) -> SideQuestionAnswer: ...

    def cancel(self) -> bool: ...

    def owns_current_task(self) -> bool: ...

    async def cancel_and_wait(self) -> bool: ...


@dataclass(frozen=True)
class SessionSideQuestionCapabilityConsumer:
    """Generation-scoped access to one Session side-question Provider."""

    facets: CapabilityFacetSet

    def __post_init__(self) -> None:
        if self.facets.requirement != SESSION_SIDE_QUESTION_REQUIREMENT:
            raise ValueError("side-question Consumer received the wrong facet view")

    async def ask(
        self,
        question: str,
        *,
        on_update: SideQuestionUpdate | None = None,
    ) -> SideQuestionAnswer:
        return await self._facet().ask(question, on_update=on_update)

    def cancel(self) -> bool:
        return self._facet().cancel()

    def owns_current_task(self) -> bool:
        return self._facet().owns_current_task()

    async def cancel_and_wait(self) -> bool:
        return await self._facet().cancel_and_wait()

    def _facet(self) -> _SideQuestionFacet:
        return cast(_SideQuestionFacet, self.facets.require(SIDE_QUESTION_FACET))


__all__ = ["SessionSideQuestionCapabilityConsumer"]
