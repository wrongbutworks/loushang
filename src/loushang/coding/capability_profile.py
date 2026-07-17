"""Coding assembly for selectable resource and capability composition runtime."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import TypeVar

from loushang.harness.capabilities.packs import (
    CapabilityPack,
    CapabilityPackComposer,
    CapabilityPackComposition,
)
from loushang.harness.capabilities.prompt import PromptSectionComposer
from loushang.harness.conversation import ConversationHeader
from loushang.harness.resources.activation import (
    ResourceActivation,
    ResourceActivationRuntime,
    SkillActivationRuntime,
)
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.runtime import (
    ProductRuntimePlan,
    ResolvedRuntimeProfile,
    RuntimeCapabilityImplementation,
    RuntimeCapabilityRegistry,
    RuntimeCapabilitySelection,
    RuntimeProfileBinder,
    RuntimeProfileBinding,
    RuntimeProfileResolver,
    RuntimeProfileSnapshot,
    standard_capability_composition_slots,
)
from loushang.protocol import JSONValue

CODING_CAPABILITY_PROFILE_METADATA_KEY = "capabilityProfile"
CODING_CAPABILITY_PRODUCT_ID = "coding"

_RESOURCE_RUNTIME_SLOT = "resource.runtime"
_PROMPT_SECTIONS_SLOT = "prompt.sections"
_SKILL_ACTIVATION_SLOT = "skill.activation"
_TOOL_PACKS_SLOT = "tool.packs"
_COMMAND_PACKS_SLOT = "command.packs"
T = TypeVar("T")
TValue = TypeVar("TValue")


@dataclass
class CodingCapabilityRuntimeBinding:
    """Product-owned wrapper around pure Harness capability implementations."""

    binding: RuntimeProfileBinding
    _binder: RuntimeProfileBinder

    @property
    def profile(self) -> ResolvedRuntimeProfile:
        return self.binding.profile

    def apply_skill_activation(
        self,
        bundle: ResourceBundle,
        disabled_skills: tuple[str, ...] | list[str],
    ) -> ResourceBundle:
        return self.skill_activation.apply(bundle, disabled_skills)

    def activate_resources(self, bundle: ResourceBundle | None) -> ResourceActivation:
        return self.resource_runtime.activate(bundle)

    def compose_prompt_sections(self) -> PromptSectionComposer:
        return self.prompt_section_composer

    def compose_tool_packs(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]:
        return self.tool_pack_composer.compose(packs)

    def compose_command_packs(
        self,
        packs: Iterable[CapabilityPack[T]],
    ) -> CapabilityPackComposition[T]:
        return self.command_pack_composer.compose(packs)

    @property
    def resource_runtime(self) -> ResourceActivationRuntime:
        return _require_value(
            self.binding.value(_RESOURCE_RUNTIME_SLOT),
            ResourceActivationRuntime,
            _RESOURCE_RUNTIME_SLOT,
        )

    @property
    def skill_activation(self) -> SkillActivationRuntime:
        return _require_value(
            self.binding.value(_SKILL_ACTIVATION_SLOT),
            SkillActivationRuntime,
            _SKILL_ACTIVATION_SLOT,
        )

    @property
    def prompt_section_composer(self) -> PromptSectionComposer:
        return _require_value(
            self.binding.value(_PROMPT_SECTIONS_SLOT),
            PromptSectionComposer,
            _PROMPT_SECTIONS_SLOT,
        )

    @property
    def tool_pack_composer(self) -> CapabilityPackComposer:
        return _require_value(
            self.binding.value(_TOOL_PACKS_SLOT),
            CapabilityPackComposer,
            _TOOL_PACKS_SLOT,
        )

    @property
    def command_pack_composer(self) -> CapabilityPackComposer:
        return _require_value(
            self.binding.value(_COMMAND_PACKS_SLOT),
            CapabilityPackComposer,
            _COMMAND_PACKS_SLOT,
        )

    def dispose(self) -> None:
        self._binder.dispose_sync(self.binding)


def coding_capability_plan() -> ProductRuntimePlan:
    """Declare Coding's current capability-composition implementations."""

    slots = tuple(
        replace(slot, allowed_sources=frozenset({"product"}))
        for slot in standard_capability_composition_slots()
    )
    return ProductRuntimePlan(
        product_id=CODING_CAPABILITY_PRODUCT_ID,
        slots=slots,
        defaults=(
            RuntimeCapabilitySelection(
                slot=_RESOURCE_RUNTIME_SLOT,
                implementation="harness.resource_activation",
                implementation_version=1,
                config={"bundle": "discovered"},
            ),
            RuntimeCapabilitySelection(
                slot=_PROMPT_SECTIONS_SLOT,
                implementation="harness.prompt_sections",
                implementation_version=1,
                config={"separator": "\n\n", "stripSections": True},
            ),
            RuntimeCapabilitySelection(
                slot=_SKILL_ACTIVATION_SLOT,
                implementation="harness.disabled_skill_activation",
                implementation_version=1,
                config={"disabledSelectors": "product-settings"},
            ),
            RuntimeCapabilitySelection(
                slot=_TOOL_PACKS_SLOT,
                implementation="harness.ordered_capability_packs",
                implementation_version=1,
                config={"conflicts": "tool-contribution-resolver"},
            ),
            RuntimeCapabilitySelection(
                slot=_COMMAND_PACKS_SLOT,
                implementation="harness.ordered_capability_packs",
                implementation_version=1,
                config={"conflicts": "command-catalog"},
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


def bind_coding_capability_runtime(
    *,
    profile: ResolvedRuntimeProfile | None = None,
) -> CodingCapabilityRuntimeBinding:
    """Bind Coding's pure default capability implementations synchronously."""

    resolved_profile = profile or resolve_coding_capability_profile()
    registry = RuntimeCapabilityRegistry(
        (
            RuntimeCapabilityImplementation(
                slot=_RESOURCE_RUNTIME_SLOT,
                implementation="harness.resource_activation",
                implementation_version=1,
                create=_create_resource_runtime,
            ),
            RuntimeCapabilityImplementation(
                slot=_PROMPT_SECTIONS_SLOT,
                implementation="harness.prompt_sections",
                implementation_version=1,
                create=_create_prompt_section_composer,
            ),
            RuntimeCapabilityImplementation(
                slot=_SKILL_ACTIVATION_SLOT,
                implementation="harness.disabled_skill_activation",
                implementation_version=1,
                create=_create_skill_activation_runtime,
            ),
            RuntimeCapabilityImplementation(
                slot=_TOOL_PACKS_SLOT,
                implementation="harness.ordered_capability_packs",
                implementation_version=1,
                create=_create_capability_pack_composer,
            ),
            RuntimeCapabilityImplementation(
                slot=_COMMAND_PACKS_SLOT,
                implementation="harness.ordered_capability_packs",
                implementation_version=1,
                create=_create_capability_pack_composer,
            ),
        )
    )
    binder = RuntimeProfileBinder(registry)
    return CodingCapabilityRuntimeBinding(
        binding=binder.bind_sync(resolved_profile),
        _binder=binder,
    )


def _create_resource_runtime(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> ResourceActivationRuntime:
    del selection, context
    return ResourceActivationRuntime()


def _create_prompt_section_composer(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> PromptSectionComposer:
    del context
    separator = selection.config.get("separator", "\n\n")
    strip_sections = selection.config.get("stripSections", True)
    if not isinstance(separator, str) or type(strip_sections) is not bool:
        raise TypeError("Coding prompt section configuration is invalid")
    return PromptSectionComposer(
        separator=separator,
        strip_sections=strip_sections,
    )


def _create_skill_activation_runtime(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> SkillActivationRuntime:
    del selection, context
    return SkillActivationRuntime()


def _create_capability_pack_composer(
    selection: RuntimeCapabilitySelection,
    context: object | None,
) -> CapabilityPackComposer:
    del selection, context
    return CapabilityPackComposer()


def _require_value(
    value: object | tuple[object, ...],
    expected_type: type[TValue],
    slot: str,
) -> TValue:
    if isinstance(value, tuple):
        if len(value) != 1:
            raise TypeError(
                f"Coding requires one selected capability implementation: {slot}"
            )
        value = value[0]
    if not isinstance(value, expected_type):
        raise TypeError(f"selected Coding capability is invalid: {slot}")
    return value


__all__ = [
    "CODING_CAPABILITY_PRODUCT_ID",
    "CODING_CAPABILITY_PROFILE_METADATA_KEY",
    "CodingCapabilityRuntimeBinding",
    "bind_coding_capability_runtime",
    "coding_capability_plan",
    "coding_capability_snapshot_metadata",
    "resolve_coding_capability_profile",
    "validate_coding_capability_snapshot",
]
