from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import pytest

from loushang.agent import Agent
from loushang.ai.api_registry import get_default_api_registry
from loushang.ai.context import NormalizedContext
from loushang.ai.json_codec import serialize_message
from loushang.ai.model import Auth, Capabilities, Model
from loushang.ai.options import CallOptions
from loushang.ai.prepared_request import PreparedModelRequest
from loushang.ai.provider.prepared_request_conformance import (
    run_prepared_request_barrier_conformance,
)
from loushang.ai.provider.protocol import ProviderRequest
from loushang.ai.types import UserMessage
from loushang.harness.capabilities import (
    MountGraphSnapshot,
    RegistrationInventorySnapshot,
)
from loushang.harness.conversation import (
    ConversationCommitResult,
    ConversationHeader,
    ConversationKey,
    MemoryConversationStore,
)
from loushang.harness.transcript import (
    MODEL_INPUT_COMPONENT_KIND,
    MODEL_INPUT_MAX_ENCODED_RECORD_BYTES,
    MODEL_INPUT_PREPARED_KIND,
    AgentTranscriptFileLayout,
    AgentTranscriptRecordFactory,
    AgentTranscriptUnitOfWork,
    ModelInputCommitContext,
    ModelInputComponent,
    ModelInputComponentReference,
    ModelInputIntegrityError,
    ModelInputRecordSizeError,
    ModelInputRuntimeReferences,
    ModelInputSnapshot,
    ModelInputTranscriptCommitter,
    create_agent_transcript_file_store,
    rebuild_model_input,
    verify_model_input,
)
from loushang.harness.transcript.model_input_types import hash_model_input_json


class _BlockingModelInputStore(MemoryConversationStore):
    def __init__(self) -> None:
        super().__init__(record_id=lambda record: record.record_id)
        self.block_appends = False
        self.committed = asyncio.Event()
        self.release = asyncio.Event()

    async def append(
        self,
        key: ConversationKey,
        record,
        *,
        expected_revision: int,
        operation_id: str,
    ) -> ConversationCommitResult:
        result = await super().append(
            key,
            record,
            expected_revision=expected_revision,
            operation_id=operation_id,
        )
        if self.block_appends:
            self.committed.set()
            await self.release.wait()
        return result


def _header(conversation_id: str = "model-input-conversation") -> ConversationHeader:
    return ConversationHeader(
        conversation_id=conversation_id,
        version=1,
        created_at="2026-08-14T00:00:00Z",
        metadata={"cwd": "/workspace"},
    )


def _runtime_references() -> ModelInputRuntimeReferences:
    graph = MountGraphSnapshot(
        schema_version=1,
        graph_id="coding:runtime-1",
        product_id="coding",
        runtime_id="runtime-1",
        profile_fingerprint="a" * 64,
        generation=3,
        roots=(),
        assembly_fingerprint="b" * 64,
        nodes=(),
    )
    inventory = RegistrationInventorySnapshot(
        schema_version=1,
        graph_id=graph.graph_id,
        runtime_id=graph.runtime_id,
        mount_generation=graph.generation,
        revision="c" * 64,
        entries=(),
    )
    return ModelInputRuntimeReferences.from_snapshots(graph, inventory)


async def _memory_transcript(
    store: MemoryConversationStore | None = None,
) -> AgentTranscriptUnitOfWork:
    resolved_store = store or MemoryConversationStore(
        record_id=lambda record: record.record_id
    )
    transcript = await AgentTranscriptUnitOfWork.create(
        resolved_store,
        ConversationKey("test", "model-input-conversation"),
        _header(),
    )
    await transcript.append_agent_message(
        UserMessage(role="user", content="hello", timestamp=1.0)
    )
    return transcript


def _context(
    transcript: AgentTranscriptUnitOfWork,
    *,
    logical_input: dict[str, object] | None = None,
) -> ModelInputCommitContext:
    assert transcript.leaf_id is not None
    return ModelInputCommitContext(
        purpose="main_turn",
        source_leaf_id=transcript.leaf_id,
        source_revision=transcript.revision,
        logical_input=logical_input
        or {
            "system_prompt": "system prompt",
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {
                    "name": "lookup",
                    "description": "Look up a value",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "request_options": {"reasoning": "medium"},
        },
    )


def _prepared(
    *,
    invocation_id: str = "invocation-1",
    attempt: int = 1,
) -> PreparedModelRequest:
    model = _model(api="model-input-test")
    request = ProviderRequest(
        model=model,
        context=NormalizedContext(system_prompt=None),
        options=None,
        base_url=model.base_url,
        invocation_id=invocation_id,
        attempt=attempt,
    )
    return PreparedModelRequest.from_provider_request(
        request,
        payload={
            "tools": [
                {
                    "name": "lookup",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
            "messages": [{"role": "user", "content": "hello"}],
            "model": model.id,
        },
        model_visible_headers={"anthropic-beta": "feature-1"},
    )


def _model(*, api: str) -> Model:
    return Model(
        id="model-input-model",
        provider="model-input-provider",
        endpoint="model-input-endpoint",
        api=api,
        base_url="https://provider.test/v1",
        auth=Auth(kind="none"),
        capabilities=Capabilities(input=("text",), output=("text",), stream=True),
    )


def test_model_input_records_are_hidden_deduplicated_and_hash_verified() -> None:
    async def scenario() -> None:
        transcript = await _memory_transcript()
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(transcript),
            runtime_references=_runtime_references(),
        )

        await committer.commit_prepared_request(_prepared())
        first_component_ids = {
            record.record_id
            for record in transcript.records
            if record.kind == MODEL_INPUT_COMPONENT_KIND
        }
        first_record_count = len(transcript.records)
        await committer.commit_prepared_request(
            _prepared(invocation_id="invocation-1", attempt=2)
        )

        component_ids = {
            record.record_id
            for record in transcript.records
            if record.kind == MODEL_INPUT_COMPONENT_KIND
        }
        prepared_records = [
            record
            for record in transcript.records
            if record.kind == MODEL_INPUT_PREPARED_KIND
        ]
        assert component_ids == first_component_ids
        assert len(transcript.records) == first_record_count + 1
        assert len(prepared_records) == 2
        assert transcript.replay_context().messages == (
            UserMessage(role="user", content="hello", timestamp=1.0),
        )

        commit = committer.commits[-1]
        rebuilt = rebuild_model_input(transcript, commit.snapshot_id)
        verification = verify_model_input(transcript, commit.snapshot_id)
        assert rebuilt.logical_input["system_prompt"] == "system prompt"
        assert list(rebuilt.prepared_payload) == ["tools", "messages", "model"]
        assert rebuilt.model_visible_headers == {"anthropic-beta": "feature-1"}
        assert verification.logical_input_matches
        assert verification.prepared_payload_matches
        assert commit.source_revision == 1
        assert commit.commit_revision == transcript.revision
        assert rebuilt.commit_revision == commit.commit_revision
        assert rebuilt.snapshot.commit_revision == commit.commit_revision

    asyncio.run(scenario())


def test_model_input_components_remain_reachable_and_reusable_after_fork() -> None:
    async def scenario() -> None:
        transcript = await _memory_transcript()
        selected_root_id = transcript.leaf_id
        assert selected_root_id is not None
        for index in range(20):
            await transcript.append_agent_message(
                UserMessage(
                    role="user",
                    content=f"discarded sibling {index}",
                    timestamp=2.0 + index,
                )
            )
        transcript.branch(selected_root_id)
        await transcript.append_agent_message(
            UserMessage(role="user", content="selected branch", timestamp=30.0)
        )
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(transcript),
            runtime_references=_runtime_references(),
        )
        await committer.commit_prepared_request(_prepared())
        original_snapshot_id = committer.commits[-1].snapshot_id
        original_commit_revision = committer.commits[-1].commit_revision
        original_component_ids = {
            record.record_id
            for record in transcript.records
            if record.kind == MODEL_INPUT_COMPONENT_KIND
        }

        fork = await transcript.fork(
            ConversationKey("test", "model-input-fork"),
            ConversationHeader(
                conversation_id="model-input-fork",
                version=1,
                created_at="2026-08-14T01:00:00Z",
                parent_conversation_id=transcript.header.conversation_id,
            ),
        )
        rebuilt = rebuild_model_input(fork, original_snapshot_id)
        assert rebuilt.snapshot.conversation_id == transcript.header.conversation_id
        assert rebuilt.logical_input["system_prompt"] == "system prompt"
        assert rebuilt.commit_revision == original_commit_revision

        fork_record_count = len(fork.records)
        fork_committer = ModelInputTranscriptCommitter(
            transcript=fork,
            context=_context(fork),
            runtime_references=_runtime_references(),
        )
        await fork_committer.commit_prepared_request(
            _prepared(invocation_id="invocation-fork")
        )

        assert len(fork.records) == fork_record_count + 1
        assert {
            record.record_id
            for record in fork.records
            if record.kind == MODEL_INPUT_COMPONENT_KIND
        } == original_component_ids
        fork_snapshot = rebuild_model_input(
            fork,
            fork_committer.commits[-1].snapshot_id,
        ).snapshot
        assert fork_snapshot.conversation_id == "model-input-fork"
        assert (
            fork_snapshot.commit_revision
            == fork_committer.commits[-1].commit_revision
        )

    asyncio.run(scenario())


def test_reconstruction_rejects_component_outside_snapshot_ancestry() -> None:
    async def scenario() -> None:
        transcript = await _memory_transcript()
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(transcript),
            runtime_references=_runtime_references(),
        )
        await committer.commit_prepared_request(_prepared())
        snapshot_id = committer.commits[-1].snapshot_id
        transcript.branch(_context_source_leaf(transcript))
        await transcript.append_agent_message(
            UserMessage(role="user", content="sibling", timestamp=2.0)
        )

        # The original snapshot remains reconstructable from its own ancestry;
        # selecting a sibling cannot make later facts eligible for it.
        rebuilt = rebuild_model_input(transcript, snapshot_id)
        assert rebuilt.snapshot.source_revision == 1

        snapshot_record = next(
            record
            for record in transcript.records
            if getattr(record.payload, "snapshot_id", None) == snapshot_id
        )
        reference = snapshot_record.payload.logical_components[0]
        object.__setattr__(reference, "record_id", transcript.leaf_id)
        with pytest.raises(ModelInputIntegrityError, match="ancestry"):
            rebuild_model_input(transcript, snapshot_id)

    asyncio.run(scenario())


def _context_source_leaf(transcript: AgentTranscriptUnitOfWork) -> str:
    first = transcript.records[0]
    return first.record_id


def test_record_limit_and_revision_conflict_fail_before_transport() -> None:
    async def oversized() -> None:
        transcript = await _memory_transcript()
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(
                transcript,
                logical_input={
                    "system_prompt": "x" * 4_096,
                    "messages": [],
                    "tools": [],
                    "request_options": {},
                },
            ),
            runtime_references=_runtime_references(),
            max_encoded_record_bytes=512,
        )

        with pytest.raises(ModelInputRecordSizeError):
            await committer.commit_prepared_request(_prepared())

        report = await run_prepared_request_barrier_conformance(committer)

        assert report.transport_calls == 0
        assert report.error is not None
        assert not any(
            record.kind in {MODEL_INPUT_COMPONENT_KIND, MODEL_INPUT_PREPARED_KIND}
            for record in transcript.records
        )

    async def conflicted() -> None:
        transcript = await _memory_transcript()
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(transcript),
            runtime_references=_runtime_references(),
        )
        await transcript.append_agent_message(
            UserMessage(role="user", content="concurrent", timestamp=2.0)
        )

        with pytest.raises(ModelInputIntegrityError):
            await committer.commit_prepared_request(_prepared())

        report = await run_prepared_request_barrier_conformance(committer)

        assert report.transport_calls == 0
        assert report.error is not None

    asyncio.run(oversized())
    asyncio.run(conflicted())


def test_model_input_hard_record_ceiling_cannot_be_bypassed() -> None:
    async def scenario() -> None:
        transcript = await _memory_transcript()
        with pytest.raises(ValueError, match="must not exceed"):
            ModelInputTranscriptCommitter(
                transcript=transcript,
                context=_context(transcript),
                runtime_references=_runtime_references(),
                max_encoded_record_bytes=(
                    MODEL_INPUT_MAX_ENCODED_RECORD_BYTES + 1
                ),
            )

        content = "x" * MODEL_INPUT_MAX_ENCODED_RECORD_BYTES
        component = ModelInputComponent(
            content_hash=hash_model_input_json(
                content,
                name="oversized Model Input component",
            ),
            content=content,
        )
        with pytest.raises(ModelInputRecordSizeError):
            await transcript.append(MODEL_INPUT_COMPONENT_KIND, component)

        record = AgentTranscriptRecordFactory().create(
            MODEL_INPUT_COMPONENT_KIND,
            component,
            parent_id=transcript.leaf_id,
        )
        with pytest.raises(ModelInputRecordSizeError):
            await transcript.commit(record)

        initial_backend = MemoryConversationStore(
            record_id=lambda item: item.record_id
        )
        initial_record = AgentTranscriptRecordFactory().create(
            MODEL_INPUT_COMPONENT_KIND,
            component,
            parent_id=None,
        )
        with pytest.raises(ModelInputRecordSizeError):
            await AgentTranscriptUnitOfWork.create(
                initial_backend,
                ConversationKey("initial", "oversized-model-input"),
                _header("oversized-model-input"),
                records=(initial_record,),
            )
        assert await initial_backend.scan("initial") == ()

    asyncio.run(scenario())


def test_model_input_snapshot_requires_the_v1_logical_surface() -> None:
    reference = ModelInputComponentReference(
        name="messages",
        record_id="component-record",
        content_hash="a" * 64,
    )
    snapshot = ModelInputSnapshot(
        snapshot_id="snapshot-1",
        invocation_id="invocation-1",
        attempt=1,
        purpose="main_turn",
        product_id="coding",
        runtime_id="runtime-1",
        mount_generation=1,
        profile_fingerprint="b" * 64,
        registration_revision="c" * 64,
        conversation_id="conversation-1",
        source_leaf_id="source-record",
        source_revision=1,
        commit_revision=2,
        provider_id="provider-1",
        model_id="model-1",
        api_id="api-1",
        endpoint_id="endpoint-1",
        logical_components=tuple(
            replace(reference, name=name)
            for name in ("system_prompt", "messages", "tools", "request_options")
        ),
        prepared_payload_components=(),
        model_visible_headers_component=replace(
            reference,
            name="model_visible_headers",
        ),
        logical_input_hash="d" * 64,
        prepared_payload_hash="e" * 64,
    )

    with pytest.raises(ValueError, match="logical components are missing"):
        replace(snapshot, logical_components=())
    with pytest.raises(ValueError, match="model_visible_headers"):
        replace(snapshot, model_visible_headers_component=reference)


@pytest.mark.parametrize(
    ("invalid_name", "invalid_value", "error"),
    (
        ("messages", {}, "messages must be an array"),
        ("tools", {}, "tools must be an array"),
        ("request_options", [], "request options must be an object"),
    ),
)
def test_reconstruction_rejects_invalid_v1_logical_component_types(
    invalid_name: str,
    invalid_value: object,
    error: str,
) -> None:
    async def scenario() -> None:
        transcript = await _memory_transcript()
        assert transcript.leaf_id is not None
        source_leaf_id = transcript.leaf_id
        source_revision = transcript.revision
        logical_input: dict[str, object] = {
            "system_prompt": "system prompt",
            "messages": [],
            "tools": [],
            "request_options": {},
        }
        logical_input[invalid_name] = invalid_value

        references: list[ModelInputComponentReference] = []
        for name, content in logical_input.items():
            component_hash = hash_model_input_json(
                content,
                name=f"invalid Model Input {name}",
            )
            commit = await transcript.append(
                MODEL_INPUT_COMPONENT_KIND,
                ModelInputComponent(
                    content_hash=component_hash,
                    content=content,
                ),
            )
            references.append(
                ModelInputComponentReference(
                    name=name,
                    record_id=commit.record.record_id,
                    content_hash=component_hash,
                )
            )

        headers_hash = hash_model_input_json(
            {},
            name="invalid Model Input headers",
        )
        headers_commit = await transcript.append(
            MODEL_INPUT_COMPONENT_KIND,
            ModelInputComponent(content_hash=headers_hash, content={}),
        )
        snapshot = ModelInputSnapshot(
            snapshot_id=f"invalid-{invalid_name}",
            invocation_id="invocation-1",
            attempt=1,
            purpose="main_turn",
            product_id="coding",
            runtime_id="runtime-1",
            mount_generation=1,
            profile_fingerprint="a" * 64,
            registration_revision="b" * 64,
            conversation_id=transcript.header.conversation_id,
            source_leaf_id=source_leaf_id,
            source_revision=source_revision,
            commit_revision=transcript.revision + 1,
            provider_id="provider-1",
            model_id="model-1",
            api_id="api-1",
            endpoint_id="endpoint-1",
            logical_components=tuple(references),
            prepared_payload_components=(),
            model_visible_headers_component=ModelInputComponentReference(
                name="model_visible_headers",
                record_id=headers_commit.record.record_id,
                content_hash=headers_hash,
            ),
            logical_input_hash=hash_model_input_json(
                logical_input,
                name="invalid logical Model Input",
            ),
            prepared_payload_hash=hash_model_input_json(
                {"model_visible_headers": {}, "payload": {}},
                name="empty prepared Model Input",
            ),
        )
        await transcript.append(MODEL_INPUT_PREPARED_KIND, snapshot)

        with pytest.raises(ModelInputIntegrityError, match=error):
            rebuild_model_input(transcript, snapshot.snapshot_id)

    asyncio.run(scenario())


def test_model_input_commit_propagates_cancellation_after_safe_append() -> None:
    async def scenario() -> None:
        backend = _BlockingModelInputStore()
        transcript = await _memory_transcript(backend)
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(transcript),
            runtime_references=_runtime_references(),
        )
        backend.block_appends = True

        task = asyncio.create_task(committer.commit_prepared_request(_prepared()))
        await backend.committed.wait()
        task.cancel()
        await asyncio.sleep(0)

        assert task.done() is False
        backend.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert any(
            record.kind == MODEL_INPUT_COMPONENT_KIND for record in transcript.records
        )
        assert not any(
            record.kind == MODEL_INPUT_PREPARED_KIND for record in transcript.records
        )

    asyncio.run(scenario())


class _AgentPreparedAdapter:
    api = "model-input-agent-test"

    def __init__(self) -> None:
        self.transport_calls = 0

    def prepare_request(self, request: ProviderRequest) -> PreparedModelRequest:
        context = request.context
        return PreparedModelRequest.from_provider_request(
            request,
            payload={
                "system": getattr(context, "system_prompt", None),
                "messages": [
                    serialize_message(message)
                    for message in getattr(context, "messages", ())
                ],
                "tools": [],
                "model": request.model.id,
            },
        )

    async def invoke_prepared_raw(
        self,
        request: ProviderRequest,
        prepared: PreparedModelRequest,
    ) -> AsyncIterator[dict[str, object]]:
        del request
        self.transport_calls += 1
        prepared.payload_for_transport()
        yield {"type": "response_start", "response_id": "response-1"}
        yield {"type": "text_delta", "text": "done"}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}

    async def invoke_raw(
        self,
        request: ProviderRequest,
    ) -> AsyncIterator[dict[str, object]]:
        prepared = self.prepare_request(request)
        async for part in self.invoke_prepared_raw(request, prepared):
            yield part


@pytest.mark.requires_host_runtime
def test_main_agent_turn_rebuilds_after_restart_and_source_deletion(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        source = tmp_path / "SYSTEM.md"
        source.write_text("durable system prompt", encoding="utf-8")
        system_prompt = source.read_text(encoding="utf-8")
        layout = AgentTranscriptFileLayout(tmp_path / "sessions")
        key = layout.key("model-input-conversation")
        transcript = await AgentTranscriptUnitOfWork.create(
            create_agent_transcript_file_store(layout),
            key,
            _header(),
        )
        await transcript.append_agent_message(
            UserMessage(role="user", content="hello", timestamp=1.0)
        )
        committer = ModelInputTranscriptCommitter(
            transcript=transcript,
            context=_context(
                transcript,
                logical_input={
                    "system_prompt": system_prompt,
                    "messages": [{"role": "user", "content": "hello"}],
                    "tools": [],
                    "request_options": {},
                },
            ),
            runtime_references=_runtime_references(),
        )
        adapter = _AgentPreparedAdapter()
        registry = get_default_api_registry()
        source_id = "test-model-input-agent-adapter"
        registry.register_api_adapter(adapter, source_id=source_id)
        agent = Agent(
            initial_state={
                "system_prompt": system_prompt,
                "model": _model(api=adapter.api),
                "thinking_level": "off",
            },
            call_options=CallOptions(prepared_request_committer=committer),
        )
        try:
            await agent.prompt("hello")
        finally:
            registry.unregister_api_adapters(source_id)
        assert adapter.transport_calls == 1
        commit = committer.commits[-1]

        source.unlink()
        restarted_layout = AgentTranscriptFileLayout(tmp_path / "sessions")
        restarted = await AgentTranscriptUnitOfWork.load(
            create_agent_transcript_file_store(restarted_layout),
            restarted_layout.key("model-input-conversation"),
        )
        rebuilt = rebuild_model_input(restarted, commit.snapshot_id)

        assert source.exists() is False
        assert rebuilt.logical_input["system_prompt"] == "durable system prompt"
        assert rebuilt.prepared_payload["system"] == "durable system prompt"
        assert verify_model_input(restarted, commit.snapshot_id).verified
        assert restarted.replay_context().messages == (
            UserMessage(role="user", content="hello", timestamp=1.0),
        )
        path = restarted_layout.resolve_path(key)
        assert path is not None
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            envelope = json.loads(line)
            if envelope.get("kind", "").startswith("model.input."):
                assert len((line + "\n").encode("utf-8")) <= 1024 * 1024

    asyncio.run(scenario())
