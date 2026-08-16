from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest

from loushang.harness.capabilities import (
    CapabilityBundleProvider,
    CapabilityBundleProviderBinding,
    CapabilityBundleValue,
    CapabilityContractRange,
    CapabilityDefinition,
    CapabilityFacetBinding,
    CapabilityGraphPlanRequest,
    CapabilityProviderContext,
    EffectiveRuntimeSkew,
    ModelSurfaceReference,
    RegistrationInventoryEntry,
    RuntimeCapabilityGraphBinder,
    RuntimeCapabilityGraphPlanner,
    RuntimeCapabilityGraphProjector,
    RuntimeCapabilityGraphRuntime,
    ScopedSourcePublicationReference,
)
from loushang.harness.capabilities.effective_runtime import (
    compose_registration_inventory,
)
from loushang.harness.runtime import (
    RegistrationIdentity,
    RegistrationLease,
    RuntimeProfileSnapshot,
    RuntimeProfileSnapshotCapability,
    RuntimeProfileSnapshotSelection,
)


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _profile(*, implementation: str, secret: str) -> RuntimeProfileSnapshot:
    return RuntimeProfileSnapshot(
        product_id="research",
        capabilities=(
            RuntimeProfileSnapshotCapability(
                slot="harness.workspace",
                shape="exclusive",
                scope="session",
                refresh_boundary="turn",
                variation_semantic="exclusive_replacement",
                selections=(
                    RuntimeProfileSnapshotSelection(
                        implementation=implementation,
                        implementation_version=1,
                        config={"credential": secret},
                        source="product",
                        layer_id="research",
                        layer_priority=100,
                        selection_priority=100,
                    ),
                ),
            ),
        ),
    )


def test_effective_view_explains_redacted_committed_facts_deterministically() -> None:
    async def scenario() -> None:
        profile = _profile(
            implementation="workspace.standard",
            secret="DO-NOT-PROJECT-profile-secret",
        )
        runtime, binder = await _runtime(
            profile=profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        graph = projector.snapshot()
        registrations = projector.registration_inventory()
        assert compose_registration_inventory(registrations, ()) == registrations
        model_surface = ModelSurfaceReference(
            schema_version=1,
            snapshot_id="model-input-v1",
            product_id="research",
            runtime_id="session-42",
            profile_fingerprint=_fingerprint(profile.to_json()),
            mount_generation=graph.generation,
            registration_revision=registrations.revision,
        )

        first = projector.effective_view(profile, model_surface=model_surface)
        second = projector.effective_view(profile, model_surface=model_surface)
        projected = projector.to_json(first)

        assert first == second
        assert first.assembly_fingerprint == second.assembly_fingerprint
        assert first.skew == ()
        assert projected == projector.to_json(second)
        assert "DO-NOT-PROJECT" not in repr(projected)
        assert "SecretWorkspace" not in repr(projected)

        capability = projector.explain(
            "harness.workspace",
            profile=profile,
            model_surface=model_surface,
        )
        profile_slot = projector.explain_profile_slot(
            profile,
            "harness.workspace",
            model_surface=model_surface,
        )
        registration = projector.explain_registration(
            "registration-v1",
            profile=profile,
            model_surface=model_surface,
        )

        assert capability.node.provider_id == "workspace.standard"
        assert capability.registrations[0].registration_id == "registration-v1"
        assert profile_slot.slot.selections[0].implementation == "workspace.standard"
        assert registration.entry.owner_id == "harness.workspace"
        assert registration.clocks == first.clocks

        await binder.dispose(runtime)

    asyncio.run(scenario())


def test_effective_diff_keeps_four_clocks_and_labels_legitimate_skew() -> None:
    async def scenario() -> None:
        mounted_profile = _profile(
            implementation="workspace.standard",
            secret="old-secret",
        )
        current_profile = _profile(
            implementation="workspace.reconfigured",
            secret="new-secret",
        )
        runtime, binder = await _runtime(
            profile=mounted_profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        before_graph = projector.snapshot()
        before_registrations = projector.registration_inventory()
        historical_model_surface = ModelSurfaceReference(
            schema_version=1,
            snapshot_id="model-input-v1",
            product_id="research",
            runtime_id="session-42",
            profile_fingerprint=_fingerprint(mounted_profile.to_json()),
            mount_generation=before_graph.generation,
            registration_revision=before_registrations.revision,
        )
        before = projector.effective_view(
            mounted_profile,
            model_surface=historical_model_surface,
        )

        await _rebind(
            runtime,
            binder,
            provider_id="workspace.replacement",
            provider_version=2,
            registration_id="registration-v2",
        )
        after = projector.effective_view(
            current_profile,
            model_surface=historical_model_surface,
        )
        diff = projector.diff(before, after)

        assert diff.profile_changed is True
        assert diff.mount_generation_changed is True
        assert diff.registration_revision_changed is True
        assert diff.model_surface_changed is False
        assert diff.replaced_capability_ids == ("harness.workspace",)
        assert diff.added_registration_ids == ("registration-v2",)
        assert diff.removed_registration_ids == ("registration-v1",)
        assert diff.before_clocks == before.clocks
        assert diff.after_clocks == after.clocks
        assert diff.before_skew == ()
        assert {item.code for item in diff.after_skew} == {
            "model_mount_reference_skew",
            "model_profile_reference_skew",
            "model_registration_reference_skew",
            "profile_mount_reference_skew",
        }
        assert all(item.classification == "clock_skew" for item in diff.after_skew)

        await binder.dispose(runtime)

    asyncio.run(scenario())


def test_registration_refresh_does_not_synthesize_a_mount_generation() -> None:
    async def scenario() -> None:
        profile = _profile(
            implementation="workspace.standard",
            secret="not-projected",
        )
        runtime, binder = await _runtime(
            profile=profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        base = projector.registration_inventory()
        model_surface = ModelSurfaceReference(
            schema_version=1,
            snapshot_id="model-input-v1",
            product_id="research",
            runtime_id="session-42",
            profile_fingerprint=_fingerprint(profile.to_json()),
            mount_generation=projector.snapshot().generation,
            registration_revision=base.revision,
        )
        before = projector.effective_view(
            profile,
            model_surface=model_surface,
        )
        refreshed = compose_registration_inventory(
            base,
            (
                RegistrationInventoryEntry(
                    registration_id="extension-command-v1",
                    surface="command",
                    public_key="review",
                    owner_kind="extension",
                    owner_id="review-extension",
                    runtime_id="session-42",
                    owner_generation=2,
                    attachment="effective",
                    state="active",
                ),
            ),
        )
        after = projector.effective_view(
            profile,
            model_surface=model_surface,
            registrations=refreshed,
        )
        diff = projector.diff(before, after)

        assert before.clocks.mount == after.clocks.mount
        assert diff.mount_generation_changed is False
        assert diff.profile_changed is False
        assert diff.registration_revision_changed is True
        assert diff.model_surface_changed is False
        assert diff.added_registration_ids == ("extension-command-v1",)
        assert [item.code for item in after.skew] == [
            "model_registration_reference_skew"
        ]

        await binder.dispose(runtime)

    asyncio.run(scenario())


def test_model_surface_dispositions_follow_mount_history_or_violation() -> None:
    async def scenario() -> None:
        profile = _profile(
            implementation="workspace.standard",
            secret="not-projected",
        )
        runtime, binder = await _runtime(
            profile=profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        graph = projector.snapshot()

        def dispositions(mount_generation: int) -> dict[str, str]:
            view = projector.effective_view(
                profile,
                model_surface=ModelSurfaceReference(
                    schema_version=1,
                    snapshot_id=f"model-input-{mount_generation}",
                    product_id="research",
                    runtime_id=graph.runtime_id,
                    profile_fingerprint=_fingerprint({"profile": "different"}),
                    mount_generation=mount_generation,
                    registration_revision=_fingerprint(
                        {"registration": "different"}
                    ),
                ),
            )
            return {item.code: item.disposition for item in view.skew}

        historical = dispositions(graph.generation - 1)
        future = dispositions(graph.generation + 1)

        assert historical["model_profile_reference_skew"] == "expected_history"
        assert historical["model_mount_reference_skew"] == "expected_history"
        assert historical["model_registration_reference_skew"] == "expected_history"
        assert future["model_profile_reference_skew"] == "invariant_violation"
        assert future["model_mount_reference_skew"] == "invariant_violation"
        assert future["model_registration_reference_skew"] == "invariant_violation"

        await binder.dispose(runtime)

    asyncio.run(scenario())


def test_effective_runtime_skew_rejects_unknown_disposition_contracts() -> None:
    with pytest.raises(ValueError, match="disposition schema"):
        EffectiveRuntimeSkew(
            code="profile_mount_reference_skew",
            left_clock="profile",
            left_value="one",
            right_clock="mount",
            right_value="two",
            disposition_schema_version=2,
        )
    with pytest.raises(ValueError, match="skew disposition"):
        EffectiveRuntimeSkew(
            code="profile_mount_reference_skew",
            left_clock="profile",
            left_value="one",
            right_clock="mount",
            right_value="two",
            disposition="unknown",  # type: ignore[arg-type]
        )


def test_historical_model_surface_from_fork_is_runtime_skew() -> None:
    async def scenario() -> None:
        profile = _profile(
            implementation="workspace.standard",
            secret="not-projected",
        )
        runtime, binder = await _runtime(
            profile=profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        registrations = projector.registration_inventory()
        view = projector.effective_view(
            profile,
            model_surface=ModelSurfaceReference(
                schema_version=1,
                snapshot_id="model-input-from-parent-session",
                product_id="research",
                runtime_id="session-parent",
                profile_fingerprint=_fingerprint(profile.to_json()),
                mount_generation=projector.snapshot().generation,
                registration_revision=registrations.revision,
            ),
        )

        assert [item.code for item in view.skew] == [
            "model_runtime_reference_skew"
        ]

        await binder.dispose(runtime)

    asyncio.run(scenario())


def test_source_publication_is_scoped_without_becoming_a_fifth_clock() -> None:
    async def scenario() -> None:
        profile = _profile(
            implementation="workspace.standard",
            secret="not-projected",
        )
        runtime, binder = await _runtime(
            profile=profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        before_reference = ScopedSourcePublicationReference(
            schema_version=1,
            owner_capability_id="harness.workspace",
            source_runtime_id="session-42",
            extension_generation=1,
            declaration_revision=1,
            resource_revision=1,
        )
        after_reference = replace(before_reference, resource_revision=2)
        before = projector.effective_view(
            profile,
            source_publication=before_reference,
        )
        after = projector.effective_view(
            profile,
            source_publication=after_reference,
        )
        diff = projector.diff(before, after)

        assert tuple(before.clocks.__dataclass_fields__) == (
            "profile",
            "mount",
            "registration",
            "model_surface",
        )
        assert before.clocks == after.clocks
        assert before.assembly_fingerprint != after.assembly_fingerprint
        assert diff.source_publication_changed is True
        assert before.skew == after.skew == ()
        assert diff.mount_generation_changed is False
        assert diff.registration_revision_changed is False
        assert diff.profile_changed is False
        explanation = projector.explain(
            "harness.workspace",
            profile=profile,
            source_publication=after_reference,
        )
        assert explanation.source_publication == after_reference

        await binder.dispose(runtime)

    asyncio.run(scenario())


def test_source_generation_skew_distinguishes_retirement_from_violation() -> None:
    async def scenario() -> None:
        profile = _profile(
            implementation="workspace.standard",
            secret="not-projected",
        )
        runtime, binder = await _runtime(
            profile=profile,
            provider_id="workspace.standard",
            provider_version=1,
            registration_id="registration-v1",
        )
        projector = RuntimeCapabilityGraphProjector(runtime)
        base = projector.registration_inventory()
        source = ScopedSourcePublicationReference(
            schema_version=1,
            owner_capability_id="harness.workspace",
            source_runtime_id="session-42",
            extension_generation=2,
            declaration_revision=2,
            resource_revision=2,
        )

        def view(attachment: str):
            inventory = compose_registration_inventory(
                base,
                (
                    RegistrationInventoryEntry(
                        registration_id=f"extension-{attachment}",
                        surface="command",
                        public_key="review",
                        owner_kind="extension",
                        owner_id="review-extension",
                        runtime_id="session-42",
                        owner_generation=1,
                        attachment=attachment,  # type: ignore[arg-type]
                        state="active",
                    ),
                ),
            )
            return projector.effective_view(
                profile,
                registrations=inventory,
                source_publication=source,
            )

        pending = next(
            item
            for item in view("pending_retirement").skew
            if item.code == "registration_source_generation_skew"
        )
        effective = next(
            item
            for item in view("effective").skew
            if item.code == "registration_source_generation_skew"
        )

        assert pending.disposition == "transitional_retirement"
        assert effective.disposition == "invariant_violation"
        assert pending.classification == effective.classification == "clock_skew"

        await binder.dispose(runtime)

    asyncio.run(scenario())


async def _runtime(
    *,
    profile: RuntimeProfileSnapshot,
    provider_id: str,
    provider_version: int,
    registration_id: str,
) -> tuple[RuntimeCapabilityGraphRuntime, RuntimeCapabilityGraphBinder]:
    runtime = RuntimeCapabilityGraphRuntime(
        product_id="research",
        runtime_id="session-42",
        profile_fingerprint=_fingerprint(profile.to_json()),
    )
    binder = RuntimeCapabilityGraphBinder()
    await _rebind(
        runtime,
        binder,
        provider_id=provider_id,
        provider_version=provider_version,
        registration_id=registration_id,
    )
    return runtime, binder


async def _rebind(
    runtime: RuntimeCapabilityGraphRuntime,
    binder: RuntimeCapabilityGraphBinder,
    *,
    provider_id: str,
    provider_version: int,
    registration_id: str,
) -> None:
    definition = CapabilityDefinition(
        capability_id="harness.workspace",
        owner_id="harness",
        contract_version=1,
        facets=("read",),
        scope="session",
        refresh_boundary="sealed",
        phase="bootstrap",
    )
    provider = CapabilityBundleProvider(
        capability_id=definition.capability_id,
        provider_id=provider_id,
        implementation_version=provider_version,
        compatible_contract=CapabilityContractRange.exact(1),
        facets=definition.facets,
        source_id="research",
        selection_rule="Product selection",
    )
    plan = RuntimeCapabilityGraphPlanner().plan(
        CapabilityGraphPlanRequest(
            product_id="research",
            roots=(definition.capability_id,),
            definitions=(definition,),
            providers=(provider,),
        )
    )

    class SecretWorkspace:
        def __repr__(self) -> str:
            return "DO-NOT-PROJECT-live-secret"

    def create(context: CapabilityProviderContext) -> CapabilityBundleValue:
        context.registrations.add(
            RegistrationLease(
                owner=context.registrations.owner,
                identity=RegistrationIdentity(
                    surface="tools",
                    public_key="read",
                    registration_id=registration_id,
                ),
                dispose=lambda: None,
            )
        )
        return CapabilityBundleValue(
            (CapabilityFacetBinding("read", SecretWorkspace()),)
        )

    await binder.bind(
        runtime,
        plan,
        (
            CapabilityBundleProviderBinding(
                provider=provider,
                scope_instance_id="session:42",
                binding_input_fingerprint=_fingerprint(provider_id),
                create=create,
            ),
        ),
    )
