from __future__ import annotations

import pytest

from loushang.harness.capabilities import (
    CapabilityPack,
    bind_capability_composition_runtime,
)
from loushang.harness.capabilities.composition_runtime import (
    DISABLED_SKILL_ACTIVATION_IMPLEMENTATION,
    ORDERED_CAPABILITY_PACKS_IMPLEMENTATION,
    PROMPT_SECTIONS_IMPLEMENTATION,
    RESOURCE_ACTIVATION_IMPLEMENTATION,
)
from loushang.harness.capabilities.prompt import PromptSection
from loushang.harness.resources.types import ResourceBundle, SkillDescriptor
from loushang.harness.runtime import (
    ProductRuntimePlan,
    RuntimeCapabilityBindingError,
    RuntimeCapabilitySelection,
    RuntimeProfileResolver,
    standard_capability_composition_slots,
)


def _profile(*, prompt_config: dict[str, object] | None = None):
    plan = ProductRuntimePlan(
        product_id="research",
        slots=standard_capability_composition_slots(),
        defaults=(
            RuntimeCapabilitySelection(
                slot="resource.runtime",
                implementation=RESOURCE_ACTIVATION_IMPLEMENTATION,
                implementation_version=1,
            ),
            RuntimeCapabilitySelection(
                slot="prompt.sections",
                implementation=PROMPT_SECTIONS_IMPLEMENTATION,
                implementation_version=1,
                config=prompt_config or {"separator": "\n", "stripSections": False},
            ),
            RuntimeCapabilitySelection(
                slot="skill.activation",
                implementation=DISABLED_SKILL_ACTIVATION_IMPLEMENTATION,
                implementation_version=1,
            ),
            RuntimeCapabilitySelection(
                slot="tool.packs",
                implementation=ORDERED_CAPABILITY_PACKS_IMPLEMENTATION,
                implementation_version=1,
            ),
            RuntimeCapabilitySelection(
                slot="command.packs",
                implementation=ORDERED_CAPABILITY_PACKS_IMPLEMENTATION,
                implementation_version=1,
            ),
        ),
    )
    return RuntimeProfileResolver().resolve(plan)


def test_standard_composition_runtime_binds_neutral_product_values(tmp_path) -> None:
    runtime = bind_capability_composition_runtime(_profile())
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

    activated = runtime.apply_skill_activation(bundle, ("review",))

    assert runtime.activate_resources(activated).active_skills() == ()
    assert (
        runtime.compose_prompt_sections()
        .compose((PromptSection("base", "Base"), PromptSection("tail", "Tail")))
        .text
        == "Base\nTail"
    )
    assert runtime.compose_tool_packs(
        (
            CapabilityPack("extension", "extension", ("extension",), priority=1),
            CapabilityPack("product", "product", ("product",), priority=2),
        )
    ).items == ("product", "extension")
    assert runtime.compose_command_packs(
        (CapabilityPack("commands", "product", ("command",)),)
    ).items == ("command",)
    runtime.dispose()


def test_standard_composition_runtime_rejects_unknown_configuration() -> None:
    profile = _profile(
        prompt_config={"separator": "\n\n", "stripSections": True, "extra": True}
    )

    with pytest.raises(RuntimeCapabilityBindingError) as exc_info:
        bind_capability_composition_runtime(profile)

    assert exc_info.value.slot == "prompt.sections"
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "configuration must contain" in str(exc_info.value.__cause__)
