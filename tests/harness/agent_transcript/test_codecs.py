from __future__ import annotations

import pytest

from loushang.ai.types import TextPart, UserMessage
from loushang.harness.agent_transcript import (
    AGENT_MESSAGE_KIND,
    APPLICATION_MESSAGE_KIND,
    COMMAND_EXECUTION_KIND,
    CONTEXT_BRANCH_SUMMARY_KIND,
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
    CONVERSATION_METADATA_PATCH_KIND,
    EXTENSION_DATA_KIND,
    MODEL_SELECTION_KIND,
    RECORD_ANNOTATION_PATCH_KIND,
    STANDARD_AGENT_TRANSCRIPT_KINDS,
    STANDARD_PAYLOAD_VERSION,
    THINKING_SELECTION_KIND,
    ApplicationMessage,
    BranchContextSummary,
    ContextCompactionCheckpoint,
    ConversationMetadataPatch,
    ExtensionData,
    ModelSelectionSnapshot,
    RecordAnnotationPatch,
    ThinkingSelectionSnapshot,
    create_agent_transcript_payload_registry,
)
from loushang.harness.conversation import CommandExecutionRecord
from loushang.harness.journal import JournalCodecError


def _payloads():
    return {
        AGENT_MESSAGE_KIND: UserMessage(
            role="user",
            content=[TextPart(type="text", text="question")],
            timestamp=1.0,
        ),
        THINKING_SELECTION_KIND: ThinkingSelectionSnapshot(level="high"),
        MODEL_SELECTION_KIND: ModelSelectionSnapshot(
            provider="provider",
            model_id="model",
            endpoint_id="endpoint",
        ),
        COMMAND_EXECUTION_KIND: CommandExecutionRecord(
            command="printf hello",
            output="hello",
            exit_code=0,
            truncated=True,
            full_output_path="/tmp/output",
            metadata={"shell": "bash"},
        ),
        CONTEXT_COMPACTION_CHECKPOINT_KIND: ContextCompactionCheckpoint(
            summary="Earlier work",
            first_kept_record_id="kept",
            tokens_before=123,
            details={"source": "automatic"},
            from_hook=False,
        ),
        CONTEXT_BRANCH_SUMMARY_KIND: BranchContextSummary(
            from_record_id="branch-leaf",
            summary="Alternative path",
            details=["one", 2],
            from_hook=True,
        ),
        APPLICATION_MESSAGE_KIND: ApplicationMessage(
            application_message_id="application-1",
            custom_type="notice",
            content=[TextPart(type="text", text="Check this")],
            timestamp=2.5,
            details={"priority": 1},
            origin="extension.alpha",
            delivery_mode="follow_up",
        ),
        EXTENSION_DATA_KIND: ExtensionData(
            extension_type="extension.alpha.state",
            data={"enabled": True},
        ),
        RECORD_ANNOTATION_PATCH_KIND: RecordAnnotationPatch(
            target_record_id="target",
            namespace="display.label",
            operation="set",
            value="Important",
        ),
        CONVERSATION_METADATA_PATCH_KIND: ConversationMetadataPatch(
            values={"title": "Investigation", "count": 2},
            removed_keys=("oldTitle",),
        ),
    }


def test_all_standard_payloads_round_trip_through_versioned_registry() -> None:
    registry = create_agent_transcript_payload_registry()

    assert registry.registered_keys == tuple(
        sorted(
            (kind, STANDARD_PAYLOAD_VERSION) for kind in STANDARD_AGENT_TRANSCRIPT_KINDS
        )
    )
    for kind, payload in _payloads().items():
        encoded = registry.encode(kind, STANDARD_PAYLOAD_VERSION, payload)
        decoded = registry.decode(kind, STANDARD_PAYLOAD_VERSION, encoded)
        assert decoded == payload


def test_registered_codec_rejects_corrupted_known_payload() -> None:
    registry = create_agent_transcript_payload_registry()

    with pytest.raises(JournalCodecError) as error:
        registry.decode(
            MODEL_SELECTION_KIND,
            STANDARD_PAYLOAD_VERSION,
            {"provider": "provider", "modelId": 3, "endpointId": None},
        )

    assert error.value.code == "invalid_known_payload"


def test_patch_contracts_distinguish_remove_from_setting_json_null() -> None:
    set_null = RecordAnnotationPatch(
        target_record_id="target",
        namespace="display.label",
        operation="set",
        value=None,
    )
    assert set_null.operation == "set"

    with pytest.raises(ValueError, match="must not include a value"):
        RecordAnnotationPatch(
            target_record_id="target",
            namespace="display.label",
            operation="remove",
            value="not allowed",
        )

    with pytest.raises(ValueError, match="set and removed together"):
        ConversationMetadataPatch(
            values={"title": "new"},
            removed_keys=("title",),
        )
