"""Focused ownership handoff for one bound transcript runtime trio."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from loushang.harness.runtime import RuntimeProfileSnapshot
from loushang.harness.transcript.compaction import (
    AgentTranscriptCompactionCapability,
)
from loushang.harness.transcript.model_input import (
    ModelInputLogicalProjection,
    ModelInputRuntimeReferences,
    ModelInputTranscriptCommitter,
    RebuiltModelInput,
)


class _TranscriptLifecycleOwner(Protocol):
    @property
    def ownership_state(self) -> str: ...

    def _begin_graph_construction(self) -> None: ...

    def _commit_graph_ownership(self) -> None: ...

    def _restore_root_ownership(self) -> None: ...

    def _rollback_unpublished_graph_ownership(self) -> None: ...

    async def _dispose_graph_owned(self) -> None: ...

    async def dispose(self) -> None: ...


@dataclass(frozen=True)
class AgentTranscriptCapabilityCandidate:
    """Narrow, single-owner view of an already-bound transcript runtime.

    The Store, transcript profile, and compaction selection share one Product
    runtime binding and therefore move into the Session graph as one unit.
    """

    _lifecycle: _TranscriptLifecycleOwner = field(
        repr=False,
        compare=False,
    )
    conversation_id: str
    runtime_profile_snapshot: RuntimeProfileSnapshot
    _get_compaction_capability: Callable[[], AgentTranscriptCompactionCapability] = (
        field(repr=False, compare=False)
    )
    _create_model_input_committer: Callable[
        [str, ModelInputLogicalProjection, ModelInputRuntimeReferences],
        ModelInputTranscriptCommitter,
    ] = field(repr=False, compare=False)
    _rebuild_model_input: Callable[[str], RebuiltModelInput] = field(
        repr=False,
        compare=False,
    )
    _publish_index_summary: Callable[[], Awaitable[None]] = field(
        repr=False,
        compare=False,
    )

    @property
    def ownership_state(self) -> str:
        return self._lifecycle.ownership_state

    def compaction_capability(self) -> AgentTranscriptCompactionCapability:
        if self.ownership_state not in {"root_owned", "graph_owned"}:
            raise RuntimeError("transcript capability candidate is unavailable")
        return self._get_compaction_capability()

    def create_model_input_committer(
        self,
        *,
        purpose: str,
        logical_input: ModelInputLogicalProjection,
        runtime_references: ModelInputRuntimeReferences,
    ) -> ModelInputTranscriptCommitter:
        return self._create_model_input_committer(
            purpose,
            logical_input,
            runtime_references,
        )

    def rebuild_model_input(self, snapshot_id: str) -> RebuiltModelInput:
        return self._rebuild_model_input(snapshot_id)

    async def publish_index_summary(self) -> None:
        await self._publish_index_summary()

    def _begin_graph_construction(self) -> None:
        self._lifecycle._begin_graph_construction()

    def _commit_graph_ownership(self) -> None:
        self._lifecycle._commit_graph_ownership()

    def _restore_root_ownership(self) -> None:
        self._lifecycle._restore_root_ownership()

    def _rollback_unpublished_graph_ownership(self) -> None:
        self._lifecycle._rollback_unpublished_graph_ownership()

    async def _dispose_graph_owned(self) -> None:
        await self._lifecycle._dispose_graph_owned()

    async def dispose_root_owned(self) -> None:
        await self._lifecycle.dispose()


__all__ = ["AgentTranscriptCapabilityCandidate"]
