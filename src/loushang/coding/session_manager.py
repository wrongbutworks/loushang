from __future__ import annotations

from loushang.coding.capability_plan import (
    coding_capability_snapshot_metadata,
    resolve_coding_capability_profile,
    validate_coding_capability_snapshot,
)
from loushang.coding.runtime_profile import (
    CodingRuntimeSessionBinding,
    CodingRuntimeSessionContext,
    bind_coding_runtime,
    coding_runtime_snapshot_metadata,
    resolve_coding_runtime_profile,
    selected_store,
    selected_transcript_profile,
    validate_coding_runtime_snapshot,
)
from loushang.harness.agent_transcript import (
    AgentTranscriptLifecycle,
    AgentTranscriptLifecycleContext,
    AgentTranscriptRuntimeBinding,
    AgentTranscriptSessionFactory,
    ProductTranscriptSession,
)
from loushang.harness.conversation import ConversationHeader
from loushang.harness.runtime import ResolvedRuntimeProfile
from loushang.protocol import JSONValue


async def _bind_coding_agent_transcript_runtime(
    context: AgentTranscriptLifecycleContext,
    runtime_profile: ResolvedRuntimeProfile,
) -> AgentTranscriptRuntimeBinding[CodingRuntimeSessionBinding]:
    coding_context = CodingRuntimeSessionContext(
        session_dir=context.session_dir,
        header=context.header,
        persist=context.persist,
        session_file=context.session_file,
    )
    binding = await bind_coding_runtime(
        profile=runtime_profile,
        context=coding_context,
    )
    return AgentTranscriptRuntimeBinding(
        store=selected_store(binding),
        key=coding_context.conversation_key,
        profile=selected_transcript_profile(binding),
        product_binding=binding,
        dispose=binding.dispose,
    )


_LIFECYCLE = AgentTranscriptLifecycle(
    bind_runtime=_bind_coding_agent_transcript_runtime
)


def _coding_header_metadata(
    runtime_profile: ResolvedRuntimeProfile,
) -> dict[str, JSONValue]:
    capability_profile = resolve_coding_capability_profile()
    return {
        **coding_runtime_snapshot_metadata(runtime_profile),
        **coding_capability_snapshot_metadata(capability_profile),
    }


def _validate_coding_restored_header(
    header: ConversationHeader,
    runtime_profile: ResolvedRuntimeProfile,
    persist: bool,
) -> None:
    snapshot = validate_coding_runtime_snapshot(header)
    capability_snapshot = validate_coding_capability_snapshot(header)
    capability_profile = resolve_coding_capability_profile()
    if persist and snapshot is not None and snapshot != runtime_profile.snapshot():
        raise ValueError(
            "Coding cannot resume a session with an unsupported runtime profile"
        )
    if (
        persist
        and capability_snapshot is not None
        and capability_snapshot != capability_profile.snapshot()
    ):
        raise ValueError(
            "Coding cannot resume a session with an unsupported capability profile"
        )


_FACTORY = AgentTranscriptSessionFactory(
    lifecycle=_LIFECYCLE,
    resolve_binding_input=resolve_coding_runtime_profile,
    header_metadata=_coding_header_metadata,
    validate_restored_header=_validate_coding_restored_header,
    session_file_factory=_LIFECYCLE.default_native_session_file,
)


class SessionManager(
    ProductTranscriptSession[ResolvedRuntimeProfile, CodingRuntimeSessionBinding]
):
    """Coding binding over the Harness-owned Agent transcript session API."""

    @classmethod
    def _session_factory(
        cls,
    ) -> AgentTranscriptSessionFactory[
        ResolvedRuntimeProfile,
        CodingRuntimeSessionBinding,
    ]:
        return _FACTORY

    @property
    def runtime_profile(self) -> ResolvedRuntimeProfile:
        return self._lifecycle_session.product_binding.profile

    def _fork_binding_input(self) -> ResolvedRuntimeProfile:
        return self.runtime_profile

    def get_runtime_capability(self, slot: str) -> object | tuple[object, ...]:
        return self._lifecycle_session.product_binding.value(slot)


__all__ = ["SessionManager"]
