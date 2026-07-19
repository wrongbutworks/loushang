"""Coding-owned assembly for the shared runtime-profile contracts.

Harness owns profile resolution and lifecycle.  Coding owns these concrete
choices because its session layout, transcript semantics, and compaction
prompt/model behavior are Product policy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from loushang.harness.agent_transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
    AgentTranscriptCompactionCapability,
    AgentTranscriptProfile,
    AgentTranscriptRecord,
    create_agent_transcript_compaction_capability,
)
from loushang.harness.agent_transcript.file_store import (
    AgentTranscriptFileLayout,
    create_agent_transcript_file_store,
)
from loushang.harness.conversation import ConversationHeader
from loushang.harness.runtime import (
    ProductRuntimePlan,
    ResolvedRuntimeProfile,
    RuntimeCapabilityImplementation,
    RuntimeCapabilityRegistry,
    RuntimeCapabilitySelection,
    RuntimeProfileBinder,
    RuntimeProfileBinding,
    RuntimeProfileSnapshot,
    standard_agent_session_slots,
)
from loushang.harness.storage import (
    ConversationKey,
    ConversationStore,
    MemoryConversationStore,
)
from loushang.protocol import JSONValue

CODING_RUNTIME_PRODUCT_ID = "coding"
CODING_RUNTIME_PROFILE_METADATA_KEY = "runtimeProfile"

_STORE_SLOT = "conversation.store"
_TRANSCRIPT_SLOT = "agent.transcript_profile"
_COMPACTION_SLOT = "context.compaction"


@dataclass(frozen=True)
class CodingRuntimeSessionContext:
    """Product data required to construct one session's selected capabilities."""

    session_dir: Path
    header: ConversationHeader
    persist: bool
    session_file: Path | None

    def __post_init__(self) -> None:
        session_dir = Path(self.session_dir).expanduser().resolve(strict=False)
        session_file = (
            Path(self.session_file).expanduser().resolve(strict=False)
            if self.session_file is not None
            else None
        )
        if self.persist and session_file is None:
            raise ValueError(
                "persistent Coding runtime contexts require a session file"
            )
        object.__setattr__(self, "session_dir", session_dir)
        object.__setattr__(self, "session_file", session_file)

    @property
    def conversation_key(self) -> ConversationKey:
        return ConversationKey(
            namespace=str(self.session_dir) if self.persist else "coding.memory",
            conversation_id=self.header.conversation_id,
        )


@dataclass
class CodingRuntimeSessionBinding:
    """The Product-owned lifetime wrapper around a Harness binding."""

    binding: RuntimeProfileBinding
    _binder: RuntimeProfileBinder

    @property
    def profile(self) -> ResolvedRuntimeProfile:
        return self.binding.profile

    def value(self, slot: str) -> object | tuple[object, ...]:
        return self.binding.value(slot)

    async def dispose(self) -> None:
        await self._binder.dispose(self.binding)


def coding_runtime_plan(*, persist: bool) -> ProductRuntimePlan:
    """Declare Coding's current session defaults as Harness selections."""

    slots = tuple(
        replace(
            slot,
            allowed_sources=(
                frozenset({"product", "oem"})
                if slot.key == _COMPACTION_SLOT
                else frozenset({"product"})
            ),
        )
        for slot in standard_agent_session_slots()
    )
    return ProductRuntimePlan(
        product_id=CODING_RUNTIME_PRODUCT_ID,
        slots=slots,
        defaults=(
            RuntimeCapabilitySelection(
                slot=_STORE_SLOT,
                implementation="coding.file" if persist else "coding.memory",
                implementation_version=1,
                config={"persistence": "file" if persist else "memory"},
            ),
            RuntimeCapabilitySelection(
                slot=_TRANSCRIPT_SLOT,
                implementation="coding.agent_transcript",
                implementation_version=1,
                config={"format": "current"},
            ),
            RuntimeCapabilitySelection(
                slot=_COMPACTION_SLOT,
                implementation=TURN_AWARE_SUMMARY_IMPLEMENTATION,
                implementation_version=TURN_AWARE_SUMMARY_VERSION,
                config={
                    "enabled": True,
                    "compactPercent": 80.0,
                    "reserveTokens": 8_192,
                    "keepRecentTokens": 32_768,
                },
            ),
        ),
    )


def resolve_coding_runtime_profile(*, persist: bool) -> ResolvedRuntimeProfile:
    from loushang.harness.runtime import RuntimeProfileResolver

    return RuntimeProfileResolver().resolve(coding_runtime_plan(persist=persist))


def coding_runtime_snapshot_metadata(
    profile: ResolvedRuntimeProfile,
) -> dict[str, JSONValue]:
    return {CODING_RUNTIME_PROFILE_METADATA_KEY: profile.snapshot().to_json()}


def validate_coding_runtime_snapshot(
    header: ConversationHeader,
) -> RuntimeProfileSnapshot | None:
    """Validate a persisted snapshot without silently interpreting another Product."""

    raw_snapshot = header.metadata.get(CODING_RUNTIME_PROFILE_METADATA_KEY)
    if raw_snapshot is None:
        return None
    snapshot = RuntimeProfileSnapshot.from_json(raw_snapshot)
    if snapshot.product_id != CODING_RUNTIME_PRODUCT_ID:
        raise ValueError(
            "Coding cannot resume a session with a runtime profile for Product "
            f"{snapshot.product_id!r}"
        )
    return snapshot


async def bind_coding_runtime(
    *,
    profile: ResolvedRuntimeProfile,
    context: CodingRuntimeSessionContext,
) -> CodingRuntimeSessionBinding:
    """Bind Coding's exact factories for one previously resolved profile."""

    registry = RuntimeCapabilityRegistry(
        (
            RuntimeCapabilityImplementation(
                slot=_STORE_SLOT,
                implementation="coding.memory",
                implementation_version=1,
                create=_create_memory_store,
            ),
            RuntimeCapabilityImplementation(
                slot=_STORE_SLOT,
                implementation="coding.file",
                implementation_version=1,
                create=_create_file_store,
            ),
            RuntimeCapabilityImplementation(
                slot=_TRANSCRIPT_SLOT,
                implementation="coding.agent_transcript",
                implementation_version=1,
                create=_create_agent_transcript_profile,
            ),
            RuntimeCapabilityImplementation(
                slot=_COMPACTION_SLOT,
                implementation=TURN_AWARE_SUMMARY_IMPLEMENTATION,
                implementation_version=TURN_AWARE_SUMMARY_VERSION,
                create=_create_agent_transcript_compaction_capability,
            ),
        )
    )
    binder = RuntimeProfileBinder(registry)
    return CodingRuntimeSessionBinding(
        binding=await binder.bind(profile, context=context),
        _binder=binder,
    )


def selected_store(
    binding: CodingRuntimeSessionBinding,
) -> ConversationStore[ConversationHeader, AgentTranscriptRecord]:
    value = binding.value(_STORE_SLOT)
    if not isinstance(value, ConversationStore):
        raise TypeError("selected Coding conversation store does not satisfy the port")
    return cast(ConversationStore[ConversationHeader, AgentTranscriptRecord], value)


def selected_transcript_profile(
    binding: CodingRuntimeSessionBinding,
) -> AgentTranscriptProfile:
    value = binding.value(_TRANSCRIPT_SLOT)
    if not isinstance(value, AgentTranscriptProfile):
        raise TypeError("selected Coding transcript profile is invalid")
    return value


def _create_memory_store(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> ConversationStore[ConversationHeader, AgentTranscriptRecord]:
    del selection
    coding_context = _require_context(context)
    if coding_context.persist:
        raise ValueError(
            "the Coding memory store is only valid for non-persistent runs"
        )
    return MemoryConversationStore(record_id=lambda record: record.record_id)


def _create_file_store(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> ConversationStore[ConversationHeader, AgentTranscriptRecord]:
    del selection
    coding_context = _require_context(context)
    if not coding_context.persist or coding_context.session_file is None:
        raise ValueError("the Coding file store requires a persistent session context")
    layout = AgentTranscriptFileLayout(coding_context.session_dir)
    layout.bind_create_path(
        coding_context.conversation_key, coding_context.session_file
    )
    return create_agent_transcript_file_store(layout)


def _create_agent_transcript_profile(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> AgentTranscriptProfile:
    del selection, context
    return AgentTranscriptProfile.default()


def _create_agent_transcript_compaction_capability(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> AgentTranscriptCompactionCapability:
    del context
    return create_agent_transcript_compaction_capability(
        implementation=selection.implementation,
        implementation_version=selection.implementation_version,
        config=selection.config,
    )


def _require_context(context: object | None) -> CodingRuntimeSessionContext:
    if not isinstance(context, CodingRuntimeSessionContext):
        raise TypeError("Coding runtime factories require CodingRuntimeSessionContext")
    return context


__all__ = [
    "CODING_RUNTIME_PRODUCT_ID",
    "CODING_RUNTIME_PROFILE_METADATA_KEY",
    "CodingRuntimeSessionBinding",
    "CodingRuntimeSessionContext",
    "bind_coding_runtime",
    "coding_runtime_plan",
    "coding_runtime_snapshot_metadata",
    "resolve_coding_runtime_profile",
    "selected_store",
    "selected_transcript_profile",
    "validate_coding_runtime_snapshot",
]
