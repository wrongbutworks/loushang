"""Coding's Product-owned capability-composition plan and session metadata."""

from __future__ import annotations

from dataclasses import replace

from loushang.harness.capabilities.composition_runtime import (
    CAPABILITY_COMPOSITION_IMPLEMENTATION_VERSION,
    DISABLED_SKILL_ACTIVATION_IMPLEMENTATION,
    ORDERED_CAPABILITY_PACKS_IMPLEMENTATION,
    PROMPT_SECTIONS_IMPLEMENTATION,
    RESOURCE_ACTIVATION_IMPLEMENTATION,
)
from loushang.harness.conversation import ConversationHeader
from loushang.harness.runtime import (
    ProductRuntimePlan,
    ResolvedRuntimeProfile,
    RuntimeCapabilitySelection,
    RuntimeProfileResolver,
    RuntimeProfileSnapshot,
    standard_capability_composition_slots,
)
from loushang.protocol import JSONValue

CODING_CAPABILITY_PROFILE_METADATA_KEY = "capabilityProfile"
CODING_CAPABILITY_PRODUCT_ID = "coding"


def coding_capability_plan() -> ProductRuntimePlan:
    """Declare Coding's current standard capability-composition selections."""

    slots = tuple(
        replace(slot, allowed_sources=frozenset({"product"}))
        for slot in standard_capability_composition_slots()
    )
    return ProductRuntimePlan(
        product_id=CODING_CAPABILITY_PRODUCT_ID,
        slots=slots,
        defaults=(
            RuntimeCapabilitySelection(
                slot="resource.runtime",
                implementation=RESOURCE_ACTIVATION_IMPLEMENTATION,
                implementation_version=CAPABILITY_COMPOSITION_IMPLEMENTATION_VERSION,
            ),
            RuntimeCapabilitySelection(
                slot="prompt.sections",
                implementation=PROMPT_SECTIONS_IMPLEMENTATION,
                implementation_version=CAPABILITY_COMPOSITION_IMPLEMENTATION_VERSION,
                config={"separator": "\n\n", "stripSections": True},
            ),
            RuntimeCapabilitySelection(
                slot="skill.activation",
                implementation=DISABLED_SKILL_ACTIVATION_IMPLEMENTATION,
                implementation_version=CAPABILITY_COMPOSITION_IMPLEMENTATION_VERSION,
            ),
            RuntimeCapabilitySelection(
                slot="tool.packs",
                implementation=ORDERED_CAPABILITY_PACKS_IMPLEMENTATION,
                implementation_version=CAPABILITY_COMPOSITION_IMPLEMENTATION_VERSION,
            ),
            RuntimeCapabilitySelection(
                slot="command.packs",
                implementation=ORDERED_CAPABILITY_PACKS_IMPLEMENTATION,
                implementation_version=CAPABILITY_COMPOSITION_IMPLEMENTATION_VERSION,
            ),
        ),
    )


def resolve_coding_capability_profile() -> ResolvedRuntimeProfile:
    return RuntimeProfileResolver().resolve(coding_capability_plan())


def coding_capability_snapshot_metadata(
    profile: ResolvedRuntimeProfile,
) -> dict[str, JSONValue]:
    return {CODING_CAPABILITY_PROFILE_METADATA_KEY: profile.snapshot().to_json()}


def validate_coding_capability_snapshot(
    header: ConversationHeader,
) -> RuntimeProfileSnapshot | None:
    raw_snapshot = header.metadata.get(CODING_CAPABILITY_PROFILE_METADATA_KEY)
    if raw_snapshot is None:
        return None
    snapshot = RuntimeProfileSnapshot.from_json(raw_snapshot)
    if snapshot.product_id != CODING_CAPABILITY_PRODUCT_ID:
        raise ValueError(
            "Coding cannot resume a session with a capability profile for Product "
            f"{snapshot.product_id!r}"
        )
    return snapshot


__all__ = [
    "CODING_CAPABILITY_PRODUCT_ID",
    "CODING_CAPABILITY_PROFILE_METADATA_KEY",
    "coding_capability_plan",
    "coding_capability_snapshot_metadata",
    "resolve_coding_capability_profile",
    "validate_coding_capability_snapshot",
]
