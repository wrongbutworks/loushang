"""Stable narrow ports across transcript candidate-to-Consumer handoff."""

from __future__ import annotations

from loushang.harness.session.session_capability_consumer import (
    SessionTranscriptCapabilityConsumer,
)
from loushang.harness.transcript.capability_candidate import (
    AgentTranscriptCapabilityCandidate,
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


class SessionTranscriptCapabilityPorts:
    """Route bootstrap reads to the candidate and live reads to typed leases."""

    def __init__(self, candidate: AgentTranscriptCapabilityCandidate) -> None:
        self._candidate: AgentTranscriptCapabilityCandidate | None = candidate
        self._consumer: SessionTranscriptCapabilityConsumer | None = None
        self._invalidated = False

    def install(self, consumer: SessionTranscriptCapabilityConsumer) -> None:
        if self._invalidated:
            raise RuntimeError("Session transcript capability ports were invalidated")
        if self._consumer is not None:
            raise RuntimeError("Session transcript capability ports are already mounted")
        if not consumer.facets.is_current:
            raise RuntimeError("Session transcript Consumer lease is stale")
        self._consumer = consumer
        self._candidate = None

    def invalidate(self) -> None:
        self._invalidated = True
        self._consumer = None
        self._candidate = None

    def create_model_input_committer(
        self,
        *,
        purpose: str,
        logical_input: ModelInputLogicalProjection,
        runtime_references: ModelInputRuntimeReferences,
    ) -> ModelInputTranscriptCommitter:
        return self._mounted().create_model_input_committer(
            purpose=purpose,
            logical_input=logical_input,
            runtime_references=runtime_references,
        )

    def rebuild_model_input(self, snapshot_id: str) -> RebuiltModelInput:
        return self._mounted().rebuild_model_input(snapshot_id)

    def compaction_capability(self) -> AgentTranscriptCompactionCapability:
        consumer = self._consumer
        if consumer is not None:
            return consumer.compaction_capability()
        candidate = self._candidate
        if candidate is not None and candidate.ownership_state == "root_owned":
            return candidate.compaction_capability()
        raise RuntimeError("Session transcript capability is not mounted")

    def _mounted(self) -> SessionTranscriptCapabilityConsumer:
        if self._invalidated:
            raise RuntimeError("Session transcript capability ports were invalidated")
        consumer = self._consumer
        if consumer is None:
            raise RuntimeError("Session transcript capability is not mounted")
        return consumer


__all__ = ["SessionTranscriptCapabilityPorts"]
