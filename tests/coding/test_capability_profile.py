from __future__ import annotations

from loushang.coding.product_plan import (
    CODING_CAPABILITY_PLAN,
    CODING_CAPABILITY_PROFILE,
    CODING_CAPABILITY_PROFILE_METADATA_KEY,
    CODING_PRODUCT_ID,
)
from loushang.harness.capabilities import (
    CapabilityPack,
    bind_capability_composition_runtime,
)
from loushang.harness.capabilities.prompt import PromptSection
from loushang.harness.conversation import ConversationHeader
from loushang.harness.resources.types import ResourceBundle, SkillDescriptor
from loushang.harness.runtime import RuntimeProfileSnapshot


def test_coding_capability_profile_binds_all_default_capabilities(tmp_path) -> None:
    profile = CODING_CAPABILITY_PROFILE
    binding = bind_capability_composition_runtime(profile)
    bundle = ResourceBundle(
        cwd=tmp_path,
        skills=[
            SkillDescriptor(
                name="review",
                source_path=tmp_path / "skills" / "review" / "SKILL.md",
                description="Review changes.",
            )
        ],
    )

    activated = binding.apply_skill_activation(bundle, ("review",))
    assert activated.skills[0].enabled is False
    assert binding.activate_resources(activated).active_skills() == ()
    assert (
        binding.compose_prompt_sections()
        .compose((PromptSection("base", "Base"), PromptSection("tail", "Tail")))
        .text
        == "Base\n\nTail"
    )
    assert binding.compose_tool_packs(
        (
            CapabilityPack("extension", "extension", ("extension",), priority=1),
            CapabilityPack("product", "product", ("product",), priority=2),
        )
    ).items == ("product", "extension")
    assert binding.compose_command_packs(
        (CapabilityPack("commands", "product", ("command",)),)
    ).items == ("command",)
    binding.dispose()


def test_coding_capability_snapshot_is_separate_from_other_header_metadata() -> None:
    profile = CODING_CAPABILITY_PROFILE
    header = ConversationHeader(
        conversation_id="session",
        version=1,
        created_at="2026-07-17T00:00:00Z",
        metadata={
            "cwd": "/workspace",
            CODING_CAPABILITY_PROFILE_METADATA_KEY: profile.snapshot().to_json(),
        },
    )

    snapshot = RuntimeProfileSnapshot.from_json(
        header.metadata[CODING_CAPABILITY_PROFILE_METADATA_KEY]
    )

    assert snapshot.product_id == CODING_PRODUCT_ID
    assert (
        header.metadata[CODING_CAPABILITY_PROFILE_METADATA_KEY]
        == profile.snapshot().to_json()
    )
    assert snapshot.to_json() == profile.snapshot().to_json()
    assert set(slot.key for slot in CODING_CAPABILITY_PLAN.slots) == {
        "resource.runtime",
        "prompt.sections",
        "skill.activation",
        "tool.packs",
        "command.packs",
        "continuity.provider_packs",
    }
    assert all(
        slot.allowed_sources == frozenset({"product"})
        for slot in CODING_CAPABILITY_PLAN.slots
    )
