"""Definition and focused Consumer requirement for ``harness.session``."""

from __future__ import annotations

from loushang.harness.capabilities.contracts import (
    CapabilityContractRange,
    CapabilityDefinition,
    CapabilityRequirement,
)

SIDE_QUESTION_FACET = "interaction.side_question"

SESSION_CAPABILITY_DEFINITION = CapabilityDefinition(
    capability_id="harness.session",
    owner_id="harness",
    contract_version=1,
    facets=(SIDE_QUESTION_FACET,),
    scope="session",
    refresh_boundary="sealed",
    phase="final",
)

SESSION_SIDE_QUESTION_REQUIREMENT = CapabilityRequirement(
    capability=SESSION_CAPABILITY_DEFINITION.capability_id,
    facets=(SIDE_QUESTION_FACET,),
    compatible_contract=CapabilityContractRange.exact(
        SESSION_CAPABILITY_DEFINITION.contract_version
    ),
)

__all__ = [
    "SESSION_CAPABILITY_DEFINITION",
    "SESSION_SIDE_QUESTION_REQUIREMENT",
    "SIDE_QUESTION_FACET",
]
