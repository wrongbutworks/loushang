from __future__ import annotations

import asyncio

import pytest

from loushang.harness.runtime import (
    AGENT_TRANSCRIPT_PROFILE_SLOT,
    COMMAND_PACKS_SLOT,
    CONTEXT_COMPACTION_SLOT,
    CONVERSATION_STORE_SLOT,
    PROMPT_SECTIONS_SLOT,
    RESOURCE_RUNTIME_SLOT,
    SKILL_ACTIVATION_SLOT,
    TOOL_PACKS_SLOT,
    ProductRuntimePlan,
    RuntimeCapabilityBindingError,
    RuntimeCapabilityImplementation,
    RuntimeCapabilityRegistry,
    RuntimeCapabilitySelection,
    RuntimeCapabilitySlot,
    RuntimeProfileAdmissionPolicy,
    RuntimeProfileBinder,
    RuntimeProfileLayer,
    RuntimeProfileLayerGrant,
    RuntimeProfileResolutionError,
    RuntimeProfileResolver,
    RuntimeProfileSnapshot,
    SealedRuntimeCapabilityError,
    standard_capability_composition_slots,
)


def _agent_plan(
    *,
    store_implementation: str = "memory",
    compaction_config: dict[str, object] | None = None,
) -> ProductRuntimePlan:
    return ProductRuntimePlan(
        product_id="research",
        slots=(
            CONVERSATION_STORE_SLOT,
            AGENT_TRANSCRIPT_PROFILE_SLOT,
            CONTEXT_COMPACTION_SLOT,
        ),
        defaults=(
            RuntimeCapabilitySelection(
                slot="conversation.store",
                implementation=store_implementation,
                implementation_version=1,
                config={"namespace": "research"},
            ),
            RuntimeCapabilitySelection(
                slot="agent.transcript_profile",
                implementation="agent-v3",
                implementation_version=1,
            ),
            RuntimeCapabilitySelection(
                slot="context.compaction",
                implementation="adaptive",
                implementation_version=1,
                config=compaction_config or {"reserve": 1024},
            ),
        ),
    )


def test_resolver_applies_source_precedence_and_preserves_snapshot_provenance() -> None:
    profile = RuntimeProfileResolver().resolve(
        _agent_plan(),
        layers=(
            RuntimeProfileLayer(
                source="extension",
                layer_id="extension:citations",
                selections=(
                    RuntimeCapabilitySelection(
                        slot="context.compaction",
                        implementation="adaptive",
                        implementation_version=1,
                        config={"reserve": 2048, "preserveCitations": True},
                    ),
                ),
            ),
            RuntimeProfileLayer(
                source="oem",
                layer_id="oem:durable-store",
                selections=(
                    RuntimeCapabilitySelection(
                        slot="conversation.store",
                        implementation="file",
                        implementation_version=1,
                        config={"root": "/sessions"},
                    ),
                ),
            ),
        ),
    )

    store = profile.capability("conversation.store").selections
    compaction = profile.capability("context.compaction").selections

    assert store[0].selection.implementation == "file"
    assert store[0].source == "oem"
    assert compaction[0].selection.config == {
        "reserve": 2048,
        "preserveCitations": True,
    }
    assert compaction[0].source == "extension"

    snapshot = RuntimeProfileSnapshot.from_json(profile.snapshot().to_json())
    assert snapshot.to_json() == profile.snapshot().to_json()
    assert snapshot.capabilities[0].selections[0].source == "oem"


def test_resolver_rejects_undeclared_and_unauthorized_layers_with_diagnostics() -> None:
    with pytest.raises(RuntimeProfileResolutionError) as exc_info:
        RuntimeProfileResolver().resolve(
            _agent_plan(),
            layers=(
                RuntimeProfileLayer(
                    source="session",
                    layer_id="session:unsafe-store",
                    selections=(
                        RuntimeCapabilitySelection(
                            slot="conversation.store",
                            implementation="redis",
                            implementation_version=1,
                        ),
                    ),
                ),
                RuntimeProfileLayer(
                    source="extension",
                    layer_id="extension:unknown",
                    selections=(
                        RuntimeCapabilitySelection(
                            slot="unknown.capability",
                            implementation="unknown",
                            implementation_version=1,
                        ),
                    ),
                ),
            ),
        )

    assert {diagnostic.code for diagnostic in exc_info.value.diagnostics} == {
        "source_not_allowed",
        "unknown_slot",
    }


def test_ordered_replaces_same_identity_while_append_only_keeps_every_contribution() -> (
    None
):
    ordered_slot = RuntimeCapabilitySlot(
        key="prompt.sections",
        shape="ordered",
        scope="session",
        refresh_boundary="sealed",
        allowed_sources=frozenset({"product", "extension"}),
    )
    append_slot = RuntimeCapabilitySlot(
        key="audit.observers",
        shape="append_only",
        scope="session",
        refresh_boundary="sealed",
        allowed_sources=frozenset({"product", "extension"}),
    )
    plan = ProductRuntimePlan(
        product_id="research",
        slots=(ordered_slot, append_slot),
        defaults=(
            RuntimeCapabilitySelection(
                slot="prompt.sections",
                implementation="sources",
                implementation_version=1,
                config={"title": "Sources"},
            ),
            RuntimeCapabilitySelection(
                slot="audit.observers",
                implementation="history",
                implementation_version=1,
            ),
        ),
    )

    profile = RuntimeProfileResolver().resolve(
        plan,
        layers=(
            RuntimeProfileLayer(
                source="extension",
                layer_id="extension:citations",
                selections=(
                    RuntimeCapabilitySelection(
                        slot="prompt.sections",
                        implementation="sources",
                        implementation_version=1,
                        config={"title": "Cited sources"},
                    ),
                    RuntimeCapabilitySelection(
                        slot="audit.observers",
                        implementation="history",
                        implementation_version=1,
                    ),
                ),
            ),
        ),
    )

    assert profile.capability("prompt.sections").selections[0].selection.config == {
        "title": "Cited sources"
    }
    assert len(profile.capability("audit.observers").selections) == 2


def test_binder_refreshes_turn_safe_slots_and_invalidates_prior_leases() -> None:
    calls: list[tuple[str, object]] = []

    async def create(selection: RuntimeCapabilitySelection, context: object) -> str:
        calls.append(("create", (selection.slot, selection.config, context)))
        return f"{selection.slot}:{selection.config}"

    async def dispose(value: object, context: object) -> None:
        calls.append(("dispose", (value, context)))

    registry = RuntimeCapabilityRegistry(
        (
            RuntimeCapabilityImplementation(
                slot="conversation.store",
                implementation="memory",
                implementation_version=1,
                create=create,
                dispose=dispose,
            ),
            RuntimeCapabilityImplementation(
                slot="agent.transcript_profile",
                implementation="agent-v3",
                implementation_version=1,
                create=create,
                dispose=dispose,
            ),
            RuntimeCapabilityImplementation(
                slot="context.compaction",
                implementation="adaptive",
                implementation_version=1,
                create=create,
                dispose=dispose,
            ),
        )
    )
    resolver = RuntimeProfileResolver()
    original = resolver.resolve(_agent_plan())
    refreshed = resolver.resolve(_agent_plan(compaction_config={"reserve": 2048}))
    binder = RuntimeProfileBinder(registry)

    async def scenario() -> None:
        binding = await binder.bind(original, context="session-1")
        lease = binding.capture()
        await binder.rebind(binding, refreshed)

        assert binding.value("context.compaction") == (
            "context.compaction:{'reserve': 2048}"
        )
        assert lease.is_current is False
        with pytest.raises(RuntimeError, match="refreshed"):
            lease.require()

        await binder.dispose(binding)
        assert binding.is_closed is True

    asyncio.run(scenario())

    assert calls == [
        ("create", ("conversation.store", {"namespace": "research"}, "session-1")),
        ("create", ("agent.transcript_profile", {}, "session-1")),
        ("create", ("context.compaction", {"reserve": 1024}, "session-1")),
        ("create", ("context.compaction", {"reserve": 2048}, "session-1")),
        (
            "dispose",
            ("context.compaction:{'reserve': 1024}", "session-1"),
        ),
        (
            "dispose",
            ("context.compaction:{'reserve': 2048}", "session-1"),
        ),
        ("dispose", ("agent.transcript_profile:{}", "session-1")),
        (
            "dispose",
            ("conversation.store:{'namespace': 'research'}", "session-1"),
        ),
    ]


def test_binder_rejects_sealed_store_replacement_before_creating_a_new_value() -> None:
    registry = RuntimeCapabilityRegistry()
    binder = RuntimeProfileBinder(registry)

    async def scenario() -> None:
        profile = RuntimeProfileResolver().resolve(_agent_plan())
        with pytest.raises(RuntimeCapabilityBindingError, match="conversation.store"):
            await binder.bind(profile)

    asyncio.run(scenario())

    # Resolution-level sealing is enforced before a replacement factory is
    # consulted.  Use factories only for the initial binding below.
    created: list[str] = []

    def create(selection: RuntimeCapabilitySelection, context: object) -> str:
        del context
        created.append(selection.implementation)
        return selection.implementation

    for selection in _agent_plan().defaults:
        registry.register(
            RuntimeCapabilityImplementation(
                slot=selection.slot,
                implementation=selection.implementation,
                implementation_version=selection.implementation_version,
                create=create,
            )
        )

    async def sealed_scenario() -> None:
        binding = await binder.bind(RuntimeProfileResolver().resolve(_agent_plan()))
        replacement = RuntimeProfileResolver().resolve(
            _agent_plan(store_implementation="file")
        )
        with pytest.raises(SealedRuntimeCapabilityError, match="conversation.store"):
            await binder.rebind(binding, replacement)
        assert binding.value("conversation.store") == "memory"

    asyncio.run(sealed_scenario())
    assert created == ["memory", "agent-v3", "adaptive"]


def test_turn_rebind_factory_failure_keeps_the_previous_binding_and_lease() -> None:
    def create(selection: RuntimeCapabilitySelection, context: object | None) -> str:
        del context
        if (
            selection.slot == "context.compaction"
            and selection.config["reserve"] == 2048
        ):
            raise RuntimeError("replacement backend is unavailable")
        return (
            f"{selection.slot}:{selection.config['reserve']}"
            if selection.slot == "context.compaction"
            else selection.slot
        )

    registry = RuntimeCapabilityRegistry(
        tuple(
            RuntimeCapabilityImplementation(
                slot=selection.slot,
                implementation=selection.implementation,
                implementation_version=selection.implementation_version,
                create=create,
            )
            for selection in _agent_plan().defaults
        )
    )
    resolver = RuntimeProfileResolver()
    binder = RuntimeProfileBinder(registry)

    async def scenario() -> None:
        binding = await binder.bind(resolver.resolve(_agent_plan()))
        lease = binding.capture()
        with pytest.raises(RuntimeCapabilityBindingError, match="context.compaction"):
            await binder.rebind(
                binding,
                resolver.resolve(_agent_plan(compaction_config={"reserve": 2048})),
            )
        assert binding.value("context.compaction") == "context.compaction:1024"
        assert lease.is_current is True
        assert lease.require().profile is binding.profile

    asyncio.run(scenario())


def test_binder_rolls_back_previously_created_values_when_later_factory_fails() -> None:
    first_slot = RuntimeCapabilitySlot(
        key="first",
        shape="single",
        scope="session",
        refresh_boundary="sealed",
        allowed_sources=frozenset({"product"}),
    )
    second_slot = RuntimeCapabilitySlot(
        key="second",
        shape="single",
        scope="session",
        refresh_boundary="sealed",
        allowed_sources=frozenset({"product"}),
    )
    profile = RuntimeProfileResolver().resolve(
        ProductRuntimePlan(
            product_id="research",
            slots=(first_slot, second_slot),
            defaults=(
                RuntimeCapabilitySelection(
                    slot="first", implementation="works", implementation_version=1
                ),
                RuntimeCapabilitySelection(
                    slot="second", implementation="fails", implementation_version=1
                ),
            ),
        )
    )
    calls: list[str] = []

    def create_first(selection: RuntimeCapabilitySelection, context: object) -> str:
        del selection, context
        calls.append("create:first")
        return "first"

    def dispose_first(value: object, context: object) -> None:
        del value, context
        calls.append("dispose:first")

    def create_second(selection: RuntimeCapabilitySelection, context: object) -> object:
        del selection, context
        calls.append("create:second")
        raise RuntimeError("no backend")

    binder = RuntimeProfileBinder(
        RuntimeCapabilityRegistry(
            (
                RuntimeCapabilityImplementation(
                    slot="first",
                    implementation="works",
                    implementation_version=1,
                    create=create_first,
                    dispose=dispose_first,
                ),
                RuntimeCapabilityImplementation(
                    slot="second",
                    implementation="fails",
                    implementation_version=1,
                    create=create_second,
                ),
            )
        )
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeCapabilityBindingError, match="second"):
            await binder.bind(profile)

    asyncio.run(scenario())
    assert calls == ["create:first", "create:second", "dispose:first"]


def test_snapshot_rejects_boolean_versions_instead_of_treating_them_as_integers() -> (
    None
):
    with pytest.raises(TypeError, match="schemaVersion"):
        RuntimeProfileSnapshot.from_json(
            {"schemaVersion": True, "productId": "research", "capabilities": []}
        )


def test_capability_composition_slots_have_deliberate_source_boundaries() -> None:
    slots = {slot.key: slot for slot in standard_capability_composition_slots()}

    assert set(slots) == {
        "resource.runtime",
        "prompt.sections",
        "skill.activation",
        "tool.packs",
        "command.packs",
    }
    assert slots == {
        "resource.runtime": RESOURCE_RUNTIME_SLOT,
        "prompt.sections": PROMPT_SECTIONS_SLOT,
        "skill.activation": SKILL_ACTIVATION_SLOT,
        "tool.packs": TOOL_PACKS_SLOT,
        "command.packs": COMMAND_PACKS_SLOT,
    }
    assert slots["resource.runtime"].allowed_sources == frozenset({"product", "oem"})
    assert slots["tool.packs"].allowed_sources == frozenset(
        {"product", "oem", "extension"}
    )
    assert slots["command.packs"].allowed_sources == frozenset(
        {"product", "oem", "extension"}
    )
    assert "session" not in slots["tool.packs"].allowed_sources


def test_admission_requires_an_explicit_grant_and_slot_permission() -> None:
    plan = ProductRuntimePlan(
        product_id="research",
        slots=(PROMPT_SECTIONS_SLOT, TOOL_PACKS_SLOT),
    )
    extension_layer = RuntimeProfileLayer(
        source="extension",
        layer_id="extension:citations",
        selections=(
            RuntimeCapabilitySelection(
                slot="prompt.sections",
                implementation="citations",
                implementation_version=1,
            ),
            RuntimeCapabilitySelection(
                slot="tool.packs",
                implementation="citation-tools",
                implementation_version=1,
            ),
        ),
    )

    untrusted = RuntimeProfileAdmissionPolicy().admit(plan, (extension_layer,))
    assert untrusted.layers == ()
    assert [diagnostic.code for diagnostic in untrusted.diagnostics] == [
        "untrusted_runtime_layer"
    ]

    policy = RuntimeProfileAdmissionPolicy(
        grants=(
            RuntimeProfileLayerGrant(
                source="extension",
                layer_id="extension:citations",
                allowed_slots=frozenset({"prompt.sections", "tool.packs"}),
                granted_permissions=frozenset({"prompt.compose"}),
            ),
        ),
        slot_permissions={"tool.packs": frozenset({"tool.execute"})},
    )
    denied = policy.admit(plan, (extension_layer,))
    assert denied.layers == ()
    assert [diagnostic.code for diagnostic in denied.diagnostics] == [
        "runtime_slot_permission_denied"
    ]

    admitted = RuntimeProfileAdmissionPolicy(
        grants=(
            RuntimeProfileLayerGrant(
                source="extension",
                layer_id="extension:citations",
                allowed_slots=frozenset({"prompt.sections", "tool.packs"}),
                granted_permissions=frozenset({"prompt.compose", "tool.execute"}),
            ),
        ),
        slot_permissions={"tool.packs": frozenset({"tool.execute"})},
    ).admit(plan, (extension_layer,))
    assert admitted.require_valid() == (extension_layer,)
