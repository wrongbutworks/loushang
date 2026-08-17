"""Focused Consumer for the side-question facet of ``harness.session``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

from loushang.harness.capabilities.graph_runtime import CapabilityFacetSet
from loushang.harness.capabilities.packs import (
    CapabilityPack,
    CapabilityPackComposition,
)
from loushang.harness.capabilities.prompt import PreparedPrompt, PromptSection
from loushang.harness.capabilities.session_contracts import (
    COMPACTION_FACET,
    CONVERSATION_STORE_FACET,
    RESOURCE_COMPOSITION_FACET,
    SESSION_RESOURCE_COMPOSITION_REQUIREMENT,
    SESSION_SIDE_QUESTION_REQUIREMENT,
    SESSION_TRANSCRIPT_REQUIREMENT,
    SIDE_QUESTION_FACET,
    TRANSCRIPT_PROFILE_FACET,
)
from loushang.harness.resources.activation import ResourceActivation
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.runtime.side_question import (
    SideQuestionAnswer,
    SideQuestionUpdate,
)
from loushang.harness.transcript.compaction import (
    AgentTranscriptCompactionCapability,
)
from loushang.harness.transcript.model_input import (
    ModelInputLogicalProjection,
    ModelInputRuntimeReferences,
    ModelInputTranscriptCommitter,
    RebuiltModelInput,
)

T = TypeVar("T")


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


class _TranscriptFacet(Protocol):
    def create_model_input_committer(
        self,
        *,
        purpose: str,
        logical_input: ModelInputLogicalProjection,
        runtime_references: ModelInputRuntimeReferences,
    ) -> ModelInputTranscriptCommitter: ...

    def rebuild_model_input(self, snapshot_id: str) -> RebuiltModelInput: ...

    def compaction_capability(self) -> AgentTranscriptCompactionCapability: ...


@dataclass(frozen=True)
class SessionTranscriptCapabilityConsumer:
    """Generation-scoped access to the adopted transcript runtime trio."""

    facets: CapabilityFacetSet

    def __post_init__(self) -> None:
        if self.facets.requirement != SESSION_TRANSCRIPT_REQUIREMENT:
            raise ValueError("transcript Consumer received the wrong facet view")
        values = tuple(
            self.facets.require(facet_id)
            for facet_id in (
                CONVERSATION_STORE_FACET,
                TRANSCRIPT_PROFILE_FACET,
                COMPACTION_FACET,
            )
        )
        if any(value is not values[0] for value in values[1:]):
            raise ValueError("transcript runtime trio must share one lifecycle facet")

    def create_model_input_committer(
        self,
        *,
        purpose: str,
        logical_input: ModelInputLogicalProjection,
        runtime_references: ModelInputRuntimeReferences,
    ) -> ModelInputTranscriptCommitter:
        return self._facet().create_model_input_committer(
            purpose=purpose,
            logical_input=logical_input,
            runtime_references=runtime_references,
        )

    def rebuild_model_input(self, snapshot_id: str) -> RebuiltModelInput:
        return self._facet().rebuild_model_input(snapshot_id)

    def compaction_capability(self) -> AgentTranscriptCompactionCapability:
        return self._facet().compaction_capability()

    def _facet(self) -> _TranscriptFacet:
        return cast(_TranscriptFacet, self.facets.require(COMPACTION_FACET))


class _ResourceCompositionFacet(Protocol):
    def activate(self, bundle: ResourceBundle | None) -> ResourceActivation: ...

    def apply_skill_activation(
        self,
        bundle: ResourceBundle,
        disabled_skills: tuple[str, ...] | list[str],
    ) -> ResourceBundle: ...

    def compose_prompt(self, sections: Iterable[PromptSection]) -> PreparedPrompt: ...

    def compose_tools(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]: ...

    def compose_commands(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]: ...


@dataclass(frozen=True)
class SessionResourceCompositionCapabilityConsumer:
    """Generation-scoped Session access to its declared Resources dependency."""

    facets: CapabilityFacetSet

    def __post_init__(self) -> None:
        if self.facets.requirement != SESSION_RESOURCE_COMPOSITION_REQUIREMENT:
            raise ValueError("Session Resources Consumer received the wrong facet view")

    def activate(self, bundle: ResourceBundle | None) -> ResourceActivation:
        return self._facet().activate(bundle)

    def apply_skill_activation(
        self,
        bundle: ResourceBundle,
        disabled_skills: tuple[str, ...] | list[str],
    ) -> ResourceBundle:
        return self._facet().apply_skill_activation(bundle, disabled_skills)

    def compose_prompt(self, sections: Iterable[PromptSection]) -> PreparedPrompt:
        return self._facet().compose_prompt(sections)

    def compose_tools(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]:
        return self._facet().compose_tools(packs)

    def compose_commands(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]:
        return self._facet().compose_commands(packs)

    def _facet(self) -> _ResourceCompositionFacet:
        return cast(
            _ResourceCompositionFacet,
            self.facets.require(RESOURCE_COMPOSITION_FACET),
        )


__all__ = [
    "SessionResourceCompositionCapabilityConsumer",
    "SessionSideQuestionCapabilityConsumer",
    "SessionTranscriptCapabilityConsumer",
]
