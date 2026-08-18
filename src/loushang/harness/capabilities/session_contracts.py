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
RESOURCE_COMPOSITION_FACET = "resource.composition"
WORKSPACE_TOOL_OPERATIONS_FACET = "workspace.tool_operations"
WORKSPACE_PROCESS_LAUNCH_FACET = "workspace.process_launch"

SESSION_CAPABILITY_DEFINITION = CapabilityDefinition(
    capability_id="harness.session",
    owner_id="harness",
    contract_version=4,
    facets=(
        SIDE_QUESTION_FACET,
        CONVERSATION_STORE_FACET,
        TRANSCRIPT_PROFILE_FACET,
        COMPACTION_FACET,
        RESOURCE_COMPOSITION_FACET,
        WORKSPACE_TOOL_OPERATIONS_FACET,
        WORKSPACE_PROCESS_LAUNCH_FACET,
    ),
    scope="session",
    refresh_boundary="sealed",
    phase="final",
)

SESSION_SIDE_QUESTION_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(SIDE_QUESTION_FACET,),
    compatible_contract=CapabilityContractRange(minimum=1, maximum=4),
)

SESSION_TRANSCRIPT_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(
        CONVERSATION_STORE_FACET,
        TRANSCRIPT_PROFILE_FACET,
        COMPACTION_FACET,
    ),
    compatible_contract=CapabilityContractRange(minimum=2, maximum=4),
)

SESSION_RESOURCE_COMPOSITION_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(RESOURCE_COMPOSITION_FACET,),
    compatible_contract=CapabilityContractRange(minimum=3, maximum=4),
)

SESSION_WORKSPACE_TOOL_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(WORKSPACE_TOOL_OPERATIONS_FACET,),
    compatible_contract=CapabilityContractRange.exact(4),
)

SESSION_WORKSPACE_PROCESS_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(WORKSPACE_PROCESS_LAUNCH_FACET,),
    compatible_contract=CapabilityContractRange.exact(4),
)

__all__ = [
    "COMPACTION_FACET",
    "CONVERSATION_STORE_FACET",
    "RESOURCE_COMPOSITION_FACET",
    "SESSION_CAPABILITY_DEFINITION",
    "SESSION_RESOURCE_COMPOSITION_REQUIREMENT",
    "SESSION_SIDE_QUESTION_REQUIREMENT",
    "SESSION_TRANSCRIPT_REQUIREMENT",
    "SESSION_WORKSPACE_PROCESS_REQUIREMENT",
    "SESSION_WORKSPACE_TOOL_REQUIREMENT",
    "SIDE_QUESTION_FACET",
    "TRANSCRIPT_PROFILE_FACET",
    "WORKSPACE_PROCESS_LAUNCH_FACET",
    "WORKSPACE_TOOL_OPERATIONS_FACET",
]
