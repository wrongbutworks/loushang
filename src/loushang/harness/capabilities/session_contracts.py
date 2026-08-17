"""Definition and focused Consumer requirement for ``harness.session``."""

from __future__ import annotations

from loushang.harness.capabilities.contracts import (
    CapabilityContractRange,
    CapabilityDefinition,
    CapabilityRequirement,
)

SIDE_QUESTION_FACET = "interaction.side_question"
CONVERSATION_STORE_FACET = "conversation.store"
TRANSCRIPT_PROFILE_FACET = "agent.transcript_profile"
COMPACTION_FACET = "context.compaction"

SESSION_CAPABILITY_DEFINITION = CapabilityDefinition(
    capability_id="harness.session",
    owner_id="harness",
    contract_version=2,
    facets=(
        SIDE_QUESTION_FACET,
        CONVERSATION_STORE_FACET,
        TRANSCRIPT_PROFILE_FACET,
        COMPACTION_FACET,
    ),
    scope="session",
    refresh_boundary="sealed",
    phase="final",
)

SESSION_SIDE_QUESTION_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(SIDE_QUESTION_FACET,),
    compatible_contract=CapabilityContractRange(minimum=1, maximum=2),
)

SESSION_TRANSCRIPT_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(
        CONVERSATION_STORE_FACET,
        TRANSCRIPT_PROFILE_FACET,
        COMPACTION_FACET,
    ),
    compatible_contract=CapabilityContractRange.exact(2),
)

__all__ = [
    "COMPACTION_FACET",
    "CONVERSATION_STORE_FACET",
    "SESSION_CAPABILITY_DEFINITION",
    "SESSION_SIDE_QUESTION_REQUIREMENT",
    "SESSION_TRANSCRIPT_REQUIREMENT",
    "SIDE_QUESTION_FACET",
    "TRANSCRIPT_PROFILE_FACET",
]
