from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from loushang.ai.model import Capabilities, Model
from loushang.coding.bootstrap import create_agent_session
from loushang.coding.capability_profile import (
    CODING_CAPABILITY_PROFILE_METADATA_KEY,
    resolve_coding_capability_profile,
)
from loushang.coding.runtime_profile import CODING_RUNTIME_PROFILE_METADATA_KEY
from loushang.coding.store import SessionManager
from loushang.coding.store.file_codec import write_session_file
from loushang.harness.agent_transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
    AgentTranscriptCompactionCapability,
    AgentTranscriptProfile,
)
from loushang.harness.runtime import RuntimeProfileSnapshot
from loushang.harness.storage import FileConversationStore, MemoryConversationStore


def _model() -> Model:
    return Model(
        id="profile-test",
        name="Profile Test",
        provider="test",
        endpoint="test",
        capabilities=Capabilities(context_window=128_000, max_tokens=4_096),
    )


def test_in_memory_session_binds_the_coding_runtime_profile_and_records_snapshot(
    tmp_path,
) -> None:
    async def scenario() -> None:
        manager = await SessionManager.new(
            session_dir=tmp_path,
            cwd="/tmp/project",
            persist=False,
        )
        snapshot = RuntimeProfileSnapshot.from_json(
            manager.header.metadata[CODING_RUNTIME_PROFILE_METADATA_KEY]
        )
        capability_snapshot = RuntimeProfileSnapshot.from_json(
            manager.header.metadata[CODING_CAPABILITY_PROFILE_METADATA_KEY]
        )

        assert manager.runtime_profile.product_id == "coding"
        assert snapshot.to_json() == manager.runtime_profile.snapshot().to_json()
        assert (
            capability_snapshot.to_json()
            == resolve_coding_capability_profile().snapshot().to_json()
        )
        assert isinstance(
            manager.get_runtime_capability("conversation.store"),
            MemoryConversationStore,
        )
        assert isinstance(
            manager.get_runtime_capability("agent.transcript_profile"),
            AgentTranscriptProfile,
        )
        assert isinstance(
            manager.get_runtime_capability("context.compaction"),
            AgentTranscriptCompactionCapability,
        )
        assert manager._transcript._profile is manager.get_runtime_capability(
            "agent.transcript_profile"
        )

        await manager.dispose_runtime_profile()
        with pytest.raises(RuntimeError, match="closed"):
            manager.get_runtime_capability("conversation.store")

    asyncio.run(scenario())


def test_persistent_session_resumes_the_snapshotted_file_profile(tmp_path) -> None:
    async def scenario() -> None:
        manager = await SessionManager.new(
            session_dir=tmp_path,
            cwd="/tmp/project",
            persist=True,
        )
        assert manager.session_file is not None
        assert isinstance(
            manager.get_runtime_capability("conversation.store"),
            FileConversationStore,
        )
        expected_snapshot = manager.runtime_profile.snapshot().to_json()
        expected_capability_snapshot = (
            resolve_coding_capability_profile().snapshot().to_json()
        )

        resumed = await SessionManager.load(manager.session_file, persist=True)

        assert resumed.runtime_profile.snapshot().to_json() == expected_snapshot
        assert (
            RuntimeProfileSnapshot.from_json(
                resumed.header.metadata[CODING_RUNTIME_PROFILE_METADATA_KEY]
            ).to_json()
            == expected_snapshot
        )
        assert (
            RuntimeProfileSnapshot.from_json(
                resumed.header.metadata[CODING_CAPABILITY_PROFILE_METADATA_KEY]
            ).to_json()
            == expected_capability_snapshot
        )
        assert isinstance(
            resumed.get_runtime_capability("conversation.store"),
            FileConversationStore,
        )

        await manager.dispose_runtime_profile()
        await resumed.dispose_runtime_profile()

    asyncio.run(scenario())


def test_persistent_session_rejects_a_different_capability_profile(tmp_path) -> None:
    async def scenario() -> None:
        manager = await SessionManager.new(
            session_dir=tmp_path,
            cwd="/tmp/project",
            persist=True,
        )
        assert manager.session_file is not None
        header = replace(
            manager.header,
            metadata={
                **manager.header.metadata,
                CODING_CAPABILITY_PROFILE_METADATA_KEY: {
                    "schemaVersion": 1,
                    "productId": "coding",
                    "capabilities": [],
                },
            },
        )
        write_session_file(manager.session_file, header, manager.get_entries())
        await manager.dispose_runtime_profile()

        with pytest.raises(ValueError, match="unsupported capability profile"):
            await SessionManager.load(manager.session_file, persist=True)

    asyncio.run(scenario())


def test_nonpersistent_open_uses_memory_without_rewriting_file_profile(
    tmp_path,
) -> None:
    async def scenario() -> None:
        manager = await SessionManager.new(
            session_dir=tmp_path,
            cwd="/tmp/project",
            persist=True,
        )
        assert manager.session_file is not None
        persisted_snapshot = manager.header.metadata[
            CODING_RUNTIME_PROFILE_METADATA_KEY
        ]

        transient = await SessionManager.load(manager.session_file, persist=False)

        assert isinstance(
            transient.get_runtime_capability("conversation.store"),
            MemoryConversationStore,
        )
        assert (
            transient.header.metadata[CODING_RUNTIME_PROFILE_METADATA_KEY]
            == persisted_snapshot
        )

        await manager.dispose_runtime_profile()
        await transient.dispose_runtime_profile()

    asyncio.run(scenario())


def test_agent_session_uses_and_disposes_selected_compaction_runtime(tmp_path) -> None:
    async def scenario() -> None:
        manager = await SessionManager.new(
            session_dir=tmp_path,
            cwd=str(tmp_path),
            persist=False,
        )
        compaction_capability = manager.get_runtime_capability("context.compaction")
        assert isinstance(compaction_capability, AgentTranscriptCompactionCapability)
        assert compaction_capability.implementation == TURN_AWARE_SUMMARY_IMPLEMENTATION
        assert compaction_capability.implementation_version == TURN_AWARE_SUMMARY_VERSION

        session = create_agent_session(session_manager=manager, model=_model())
        capability_runtime = session._capability_runtime

        assert session._compaction_controller.compaction_capability is compaction_capability
        assert capability_runtime is not None
        assert (
            session._tool_controller.prompt_section_composer
            is capability_runtime.prompt_section_composer
        )
        assert (
            session._command_controller.pack_composer
            is capability_runtime.command_pack_composer
        )

        await session.dispose()
        assert capability_runtime.binding.is_closed
        with pytest.raises(RuntimeError, match="closed"):
            manager.get_runtime_capability("context.compaction")

    asyncio.run(scenario())
