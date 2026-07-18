from __future__ import annotations

from loushang.harness.conversation.catalog import (
    ConversationCatalog,
    ProjectionQuery,
)
from loushang.harness.conversation.native_codec import (
    CONVERSATION_ENVELOPE_TYPE,
    CONVERSATION_RECORD_TYPE,
    ConversationPayloadCodec,
    ConversationPayloadCodecRegistry,
    FunctionalConversationPayloadCodec,
    NativeConversationHeaderCodec,
    NativeConversationRecordCodec,
)
from loushang.harness.conversation.ports import (
    ConversationFolder,
    ConversationHeaderCodec,
    ConversationProjector,
    ConversationRecordCodec,
    FunctionalConversationFolder,
    FunctionalConversationHeaderCodec,
    FunctionalConversationProjector,
    FunctionalConversationRecordCodec,
)
from loushang.harness.conversation.replay import (
    ConversationCheckpoint,
    ConversationReplayFolder,
    ConversationReplayPorts,
    ConversationReplayProjection,
    MissingCheckpointPolicy,
)
from loushang.harness.conversation.repository import (
    ConversationRepository,
    fold_records,
)
from loushang.harness.conversation.types import (
    BranchDelta,
    CommandExecutionRecord,
    ConversationHeader,
    ConversationRecord,
    ConversationTreeNode,
    OpaquePayload,
)

__all__ = [
    "BranchDelta",
    "CommandExecutionRecord",
    "CONVERSATION_ENVELOPE_TYPE",
    "CONVERSATION_RECORD_TYPE",
    "ConversationCatalog",
    "ConversationCheckpoint",
    "ConversationFolder",
    "ConversationHeader",
    "ConversationHeaderCodec",
    "ConversationProjector",
    "ConversationPayloadCodec",
    "ConversationPayloadCodecRegistry",
    "ConversationRecord",
    "ConversationRecordCodec",
    "ConversationReplayFolder",
    "ConversationReplayPorts",
    "ConversationReplayProjection",
    "ConversationRepository",
    "ConversationTreeNode",
    "FunctionalConversationFolder",
    "FunctionalConversationHeaderCodec",
    "FunctionalConversationProjector",
    "FunctionalConversationPayloadCodec",
    "FunctionalConversationRecordCodec",
    "MissingCheckpointPolicy",
    "NativeConversationHeaderCodec",
    "NativeConversationRecordCodec",
    "OpaquePayload",
    "ProjectionQuery",
    "fold_records",
]
