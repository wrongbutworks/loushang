"""Contract tests for the CLA7d stable continuity reference boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from loushang.harness.continuity import (
    ActivationLeaseStateError,
    BoundContinuityProvider,
    CallbackPreparedActivationLease,
    ContinuityHub,
    ContinuityPreview,
    ContinuityPreviewSection,
    ContinuityProviderDescriptor,
    ContinuityQuery,
    ContinuitySummary,
    ContinuityTarget,
    ExperienceComposition,
    ExperienceDescriptor,
    PreparedActivationLease,
    ProviderPage,
    ProviderPageItem,
    StaleContinuityReferenceError,
    consume_prepared_activation,
)
from loushang.harness.continuity.reference import ContinuityObservationDescriptor
from loushang.harness.runtime import (
    ProductRuntimePlan,
    ResolvedRuntimeSelection,
    RuntimeCapabilitySelection,
    RuntimeProfileResolver,
)


def _summary(provider_id: str, opaque_id: str) -> ContinuitySummary:
    domain = provider_id.split(".", maxsplit=1)[0]
    return ContinuitySummary(
        target=ContinuityTarget(
            provider_id=provider_id,
            opaque_id=opaque_id,
            revision="1",
        ),
        domain_ids=(domain,),
        primary_domain_id=domain,
        title=f"Session {opaque_id}",
        updated_at="2026-08-18T00:00:00Z",
        created_at="2026-08-17T00:00:00Z",
    )


@dataclass
class _Provider:
    provider_id: str
    summaries: tuple[ContinuitySummary, ...] = ()
    consume_delay: float = 0.0
    query_delay: float = 0.0
    queries: list[object] = field(default_factory=list)
    aborts: list[str] = field(default_factory=list)

    @property
    def descriptor(self) -> ContinuityProviderDescriptor:
        domain = self.provider_id.split(".", maxsplit=1)[0]
        return ContinuityProviderDescriptor(
            provider_id=self.provider_id,
            experience_id="studio",
            domain_ids=(domain,),
            primary_domain_id=domain,
            label=self.provider_id,
            supported_sorts=("updated", "created"),
        )

    async def query(self, request: object) -> ProviderPage:
        self.queries.append(request)
        if self.query_delay:
            await asyncio.sleep(self.query_delay)
        return ProviderPage(
            items=tuple(
                ProviderPageItem(summary=summary, after_cursor=str(index + 1))
                for index, summary in enumerate(self.summaries)
            ),
            has_more=False,
            index_state="fresh",
            index_generation="generation-1",
            query_snapshot="snapshot-1",
        )

    async def preview(self, target: ContinuityTarget) -> ContinuityPreview:
        return ContinuityPreview(
            target=target,
            revision=target.revision,
            heading=target.opaque_id,
            sections=(ContinuityPreviewSection(kind="text", text="preview"),),
        )

    async def prepare(self, target: ContinuityTarget) -> PreparedActivationLease:
        async def consume() -> object:
            if self.consume_delay:
                await asyncio.sleep(self.consume_delay)
            return target.opaque_id

        async def abort() -> None:
            self.aborts.append(target.opaque_id)

        return CallbackPreparedActivationLease(
            target=target,
            disposition="in_place",
            consume=consume,
            abort=abort,
        )


def _hub(*providers: _Provider) -> ContinuityHub:
    profile = RuntimeProfileResolver().resolve(
        ProductRuntimePlan(product_id="studio", slots=())
    )
    bound = tuple(
        BoundContinuityProvider(
            provider=provider,
            provenance=ResolvedRuntimeSelection(
                selection=RuntimeCapabilitySelection(
                    slot="continuity.provider_packs",
                    implementation=f"test-{index}",
                    implementation_version=1,
                ),
                source="product",
                layer_id="product:studio",
                layer_priority=0,
            ),
        )
        for index, provider in enumerate(providers)
    )
    domains = tuple(
        dict.fromkeys(
            provider.provider_id.split(".", maxsplit=1)[0] for provider in providers
        )
    )
    return ContinuityHub(
        ExperienceComposition(
            experience=ExperienceDescriptor(
                experience_id="studio",
                label="Studio",
                domain_ids=domains,
                default_domain_id=domains[0],
            ),
            capability_profile=profile,
            continuity_providers=bound,
        ),
        cursor_secret=b"test-secret",
    )


def test_reference_verbs_delegate_to_hub() -> None:
    asyncio.run(_reference_verbs_delegate_to_hub())


async def _reference_verbs_delegate_to_hub() -> None:
    provider = _Provider("coding.sessions", (_summary("coding.sessions", "s-1"),))
    hub = _hub(provider)
    reference = hub.reference()

    page = await reference.query(ContinuityQuery())
    assert [summary.title for summary in page.items] == ["Session s-1"]

    target = page.items[0].target
    preview = await reference.preview(target)
    assert preview.heading == "s-1"

    lease = await reference.prepare(target)
    assert isinstance(lease, PreparedActivationLease)
    assert await consume_prepared_activation(lease) == "s-1"


def test_reference_observation_descriptor_is_frozen_and_survives_close() -> None:
    asyncio.run(_reference_observation_descriptor_is_frozen_and_survives_close())


async def _reference_observation_descriptor_is_frozen_and_survives_close() -> (
    None
):
    hub = _hub(
        _Provider("coding.sessions", (_summary("coding.sessions", "s-1"),)),
        _Provider("design.canvases", (_summary("design.canvases", "d-1"),)),
    )
    reference = hub.reference()
    observation = reference.observation
    assert isinstance(observation, ContinuityObservationDescriptor)
    assert observation.experience.domain_ids == ("coding", "design")
    assert [descriptor.provider_id for descriptor in observation.providers] == [
        "coding.sessions",
        "design.canvases",
    ]
    assert all(
        "created" in descriptor.supported_sorts
        for descriptor in observation.providers
    )

    await hub.close()
    assert reference.observation is observation
    assert reference.observation.experience.domain_ids == ("coding", "design")


def test_release_stales_reference_without_touching_authority() -> None:
    asyncio.run(_release_stales_reference_without_touching_authority())


async def _release_stales_reference_without_touching_authority() -> None:
    provider = _Provider("coding.sessions", (_summary("coding.sessions", "s-1"),))
    hub = _hub(provider)
    reference = hub.reference()

    reference.release()
    reference.release()
    assert reference.released
    with pytest.raises(StaleContinuityReferenceError):
        await reference.query(ContinuityQuery())

    # The authority itself is unaffected; other references still work.
    other = hub.reference()
    page = await other.query(ContinuityQuery())
    assert len(page.items) == 1
    await hub.close()


def test_close_stales_references_and_new_issuance_fails() -> None:
    asyncio.run(_close_stales_references_and_new_issuance_fails())


async def _close_stales_references_and_new_issuance_fails() -> None:
    provider = _Provider("coding.sessions", (_summary("coding.sessions", "s-1"),))
    hub = _hub(provider)
    reference = hub.reference()

    await hub.close()
    await hub.close()
    assert hub.closing

    with pytest.raises(StaleContinuityReferenceError):
        await reference.query(ContinuityQuery())
    with pytest.raises(StaleContinuityReferenceError):
        await reference.preview(
            ContinuityTarget(
                provider_id="coding.sessions", opaque_id="s-1", revision="1"
            )
        )
    with pytest.raises(StaleContinuityReferenceError):
        hub.reference()
    # The late verb never reached the provider.
    assert len(provider.queries) == 0


def test_close_joins_in_flight_reference_operation() -> None:
    asyncio.run(_close_joins_in_flight_reference_operation())


async def _close_joins_in_flight_reference_operation() -> None:
    provider = _Provider(
        "coding.sessions",
        (_summary("coding.sessions", "s-1"),),
        query_delay=0.05,
    )
    hub = _hub(provider)
    reference = hub.reference()

    verb = asyncio.create_task(reference.query(ContinuityQuery()))
    await asyncio.sleep(0)  # let the verb admit and reach the provider
    close = asyncio.create_task(hub.close())
    await asyncio.sleep(0.01)
    assert not close.done()  # close waits for the in-flight verb

    page = await verb
    await close
    assert len(page.items) == 1
    assert len(provider.queries) == 1


def test_verb_admitted_after_close_start_never_reaches_provider() -> None:
    asyncio.run(_verb_admitted_after_close_start_never_reaches_provider())


async def _verb_admitted_after_close_start_never_reaches_provider() -> None:
    provider = _Provider(
        "coding.sessions",
        (_summary("coding.sessions", "s-1"),),
        query_delay=0.05,
    )
    hub = _hub(provider)
    reference = hub.reference()

    in_flight = asyncio.create_task(reference.query(ContinuityQuery()))
    await asyncio.sleep(0)
    close = asyncio.create_task(hub.close())
    await asyncio.sleep(0.01)  # close has started but is still joining

    with pytest.raises(StaleContinuityReferenceError):
        await reference.query(ContinuityQuery())
    await in_flight
    await close
    assert len(provider.queries) == 1  # only the pre-close verb arrived


def test_concurrent_closes_converge() -> None:
    asyncio.run(_concurrent_closes_converge())


async def _concurrent_closes_converge() -> None:
    hub = _hub(_Provider("coding.sessions", (_summary("coding.sessions", "s-1"),)))
    reference = hub.reference()
    await asyncio.gather(hub.close(), hub.close(), hub.close())
    with pytest.raises(StaleContinuityReferenceError):
        await reference.query(ContinuityQuery())


def test_cancelled_close_converges_and_retry_completes() -> None:
    asyncio.run(_cancelled_close_converges_and_retry_completes())


async def _cancelled_close_converges_and_retry_completes() -> None:
    provider = _Provider(
        "coding.sessions",
        (_summary("coding.sessions", "s-1"),),
        query_delay=0.1,
    )
    hub = _hub(provider)
    reference = hub.reference()

    verb = asyncio.create_task(reference.query(ContinuityQuery()))
    await asyncio.sleep(0)
    close = asyncio.create_task(hub.close())
    await asyncio.sleep(0.02)
    close.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close
    assert hub.closing  # staled, but not closed

    page = await verb  # the admitted verb still completes
    assert len(page.items) == 1

    await hub.close()  # retry converges
    with pytest.raises(StaleContinuityReferenceError):
        await reference.query(ContinuityQuery())


def test_close_aborts_unconsumed_activation_lease() -> None:
    asyncio.run(_close_aborts_unconsumed_activation_lease())


async def _close_aborts_unconsumed_activation_lease() -> None:
    provider = _Provider("coding.sessions", (_summary("coding.sessions", "s-1"),))
    hub = _hub(provider)
    reference = hub.reference()
    target = ContinuityTarget(
        provider_id="coding.sessions", opaque_id="s-1", revision="1"
    )
    lease = await reference.prepare(target)

    await hub.close()

    assert provider.aborts == ["s-1"]
    with pytest.raises(ActivationLeaseStateError):
        await lease.consume()


def test_consume_after_close_start_fails_and_settles_lease() -> None:
    asyncio.run(_consume_after_close_start_fails_and_settles_lease())


async def _consume_after_close_start_fails_and_settles_lease() -> None:
    provider = _Provider(
        "coding.sessions",
        (_summary("coding.sessions", "s-1"),),
        consume_delay=0.05,
    )
    hub = _hub(provider)
    reference = hub.reference()
    target = ContinuityTarget(
        provider_id="coding.sessions", opaque_id="s-1", revision="1"
    )

    # One lease is consumed before close begins; it runs to completion.
    in_flight_lease = await reference.prepare(target)
    consumed = asyncio.create_task(in_flight_lease.consume())
    await asyncio.sleep(0)

    # A second lease remains unconsumed when close begins.
    waiting_lease = await reference.prepare(target)
    await hub.close()

    assert await consumed == "s-1"
    with pytest.raises(ActivationLeaseStateError):
        await waiting_lease.consume()
    assert provider.aborts == ["s-1"]  # only the unconsumed lease was aborted


def test_synthetic_session_holder_release_and_force_stale_paths() -> None:
    asyncio.run(_synthetic_session_holder_release_and_force_stale_paths())


async def _synthetic_session_holder_release_and_force_stale_paths() -> None:
    provider = _Provider("coding.sessions", (_summary("coding.sessions", "s-1"),))
    hub = _hub(provider)

    cooperative = hub.reference()
    abandoned = hub.reference()

    # Session shutdown releases its reference before authority close.
    cooperative.release()
    with pytest.raises(StaleContinuityReferenceError):
        await cooperative.query(ContinuityQuery())

    # The abandoned holder never releases; authority close must still succeed
    # and force-stale the reference.
    await hub.close()
    with pytest.raises(StaleContinuityReferenceError):
        await abandoned.query(ContinuityQuery())
