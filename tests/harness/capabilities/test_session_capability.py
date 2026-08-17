from __future__ import annotations

import asyncio
import hashlib

import pytest

from loushang.harness.capabilities import (
    CapabilityGraphPlanRequest,
    RuntimeCapabilityGraphBinder,
    RuntimeCapabilityGraphPlanner,
    RuntimeCapabilityGraphRuntime,
    standard_capability_composition_plan,
)
from loushang.harness.capabilities.session_contracts import (
    SESSION_CAPABILITY_DEFINITION,
    SESSION_SIDE_QUESTION_REQUIREMENT,
)
from loushang.harness.runtime import (
    ResolvedRuntimeProfile,
    RuntimeProfileResolver,
    SideQuestionAnswer,
)
from loushang.harness.session.legacy_side_question import bind_legacy_side_question
from loushang.harness.session.session_capability_consumer import (
    SessionSideQuestionCapabilityConsumer,
)
from loushang.harness.session.session_capability_provider import (
    session_side_question_provider_binding,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _candidate():  # type: ignore[no-untyped-def]
    profile = RuntimeProfileResolver().resolve(
        standard_capability_composition_plan(product_id="research")
    )
    return bind_legacy_side_question(profile)


def _plan(binding):  # type: ignore[no-untyped-def]
    return RuntimeCapabilityGraphPlanner().plan(
        CapabilityGraphPlanRequest(
            product_id="research",
            roots=(SESSION_CAPABILITY_DEFINITION.capability_id,),
            definitions=(SESSION_CAPABILITY_DEFINITION,),
            providers=(binding.provider,),
        )
    )


class _Provider:
    def __init__(self) -> None:
        self.cancel_calls = 0

    async def ask(self, question, *, on_update=None):  # type: ignore[no-untyped-def]
        if on_update is not None:
            await on_update("update")
        return SideQuestionAnswer(text=question)

    def cancel(self) -> None:
        self.cancel_calls += 1


def test_session_side_question_candidate_transfers_to_one_generation_lease() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        selected = _Provider()
        binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=candidate,
            bind_provider=lambda _factory: selected,
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()

        await binder.bind(runtime, _plan(binding), (binding,))
        consumer = SessionSideQuestionCapabilityConsumer(
            runtime.capture(SESSION_SIDE_QUESTION_REQUIREMENT)
        )

        assert candidate.ownership_state == "graph_owned"
        assert (await consumer.ask("status?")).text == "status?"
        assert runtime.snapshot is not None
        assert SESSION_CAPABILITY_DEFINITION.phase == "final"
        assert tuple(node.capability_id for node in runtime.snapshot.nodes) == (
            "harness.session",
        )

        await binder.dispose(runtime)

        assert candidate.ownership_state == "disposed"
        with pytest.raises(RuntimeError, match="disposed"):
            await consumer.ask("again")

    asyncio.run(scenario())


def test_session_side_question_reuse_leaves_new_candidate_root_owned() -> None:
    async def scenario() -> None:
        first_candidate = _candidate()
        first_binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=first_candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(runtime, _plan(first_binding), (first_binding,))

        rejected_candidate = _candidate()
        rejected_binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=rejected_candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        result = await binder.bind(
            runtime,
            _plan(rejected_binding),
            (rejected_binding,),
        )

        assert result.reused_capability_ids == ("harness.session",)
        assert rejected_candidate.ownership_state == "root_owned"
        rejected_candidate.dispose()
        assert rejected_candidate.ownership_state == "disposed"
        assert first_candidate.ownership_state == "graph_owned"

        await binder.dispose(runtime)
        assert first_candidate.ownership_state == "disposed"

    asyncio.run(scenario())


def test_session_side_question_optional_absence_is_a_mounted_unavailable_facet() -> (
    None
):
    async def scenario() -> None:
        candidate = bind_legacy_side_question(
            ResolvedRuntimeProfile(product_id="research", capabilities=())
        )
        binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(runtime, _plan(binding), (binding,))
        consumer = SessionSideQuestionCapabilityConsumer(
            runtime.capture(SESSION_SIDE_QUESTION_REQUIREMENT)
        )

        assert consumer.cancel() is False
        with pytest.raises(RuntimeError, match="not available"):
            await consumer.ask("status?")

        await binder.dispose(runtime)
        assert candidate.ownership_state == "disposed"

    asyncio.run(scenario())


def test_session_side_question_fingerprint_excludes_live_binding_callback() -> None:
    first_candidate = _candidate()
    second_candidate = _candidate()
    third_candidate = _candidate()
    try:
        first = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=first_candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        second = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=second_candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        other_scope = session_side_question_provider_binding(
            scope_instance_id="session:other",
            staged_candidate=third_candidate,
            bind_provider=lambda _factory: _Provider(),
        )

        assert first.binding_input_fingerprint == second.binding_input_fingerprint
        assert first.binding_input_fingerprint != other_scope.binding_input_fingerprint
    finally:
        first_candidate.dispose()
        second_candidate.dispose()
        third_candidate.dispose()


def test_session_side_question_construction_failure_restores_root_owner() -> None:
    async def scenario() -> None:
        candidate = _candidate()

        def fail(_factory):  # type: ignore[no-untyped-def]
            raise RuntimeError("cannot bind side-question Provider")

        binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=candidate,
            bind_provider=fail,
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )

        with pytest.raises(RuntimeError, match="provider_construction_failed"):
            await RuntimeCapabilityGraphBinder().bind(
                runtime,
                _plan(binding),
                (binding,),
            )

        assert candidate.ownership_state == "root_owned"
        assert runtime.snapshot is None
        candidate.dispose()
        assert candidate.ownership_state == "disposed"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("cancellation_point", "state_after_bind"),
    (("graph_constructing", "root_owned"), ("prepublication", "disposed")),
)
def test_session_side_question_cancellation_has_one_cleanup_owner(
    cancellation_point: str,
    state_after_bind: str,
) -> None:
    async def scenario() -> None:
        candidate = _candidate()
        original_commit = candidate._commit_graph_ownership

        def cancel_during_commit() -> None:
            if cancellation_point == "graph_constructing":
                raise asyncio.CancelledError
            original_commit()
            task = asyncio.current_task()
            assert task is not None
            task.cancel()

        candidate._commit_graph_ownership = cancel_during_commit  # type: ignore[method-assign]
        binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )

        with pytest.raises(asyncio.CancelledError):
            await RuntimeCapabilityGraphBinder().bind(
                runtime,
                _plan(binding),
                (binding,),
            )

        assert candidate.ownership_state == state_after_bind
        if candidate.ownership_state == "root_owned":
            candidate.dispose()
        assert candidate.ownership_state == "disposed"
        assert runtime.snapshot is None

    asyncio.run(scenario())


def test_session_side_question_graph_retries_only_failed_candidate_cleanup() -> None:
    async def scenario() -> None:
        candidate = _candidate()
        original_dispose = candidate._binder.dispose_sync
        attempts = 0

        def fail_once(binding):  # type: ignore[no-untyped-def]
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient side-question cleanup failure")
            original_dispose(binding)

        candidate._binder.dispose_sync = fail_once  # type: ignore[method-assign]
        binding = session_side_question_provider_binding(
            scope_instance_id="session:research",
            staged_candidate=candidate,
            bind_provider=lambda _factory: _Provider(),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(runtime, _plan(binding), (binding,))

        first_codes = await binder.dispose(runtime)

        assert first_codes == ("provider_retirement_failed",)
        assert runtime.has_pending_retirements is True
        assert candidate.ownership_state == "graph_owned"

        second_codes = await binder.dispose(runtime)

        assert second_codes == ()
        assert runtime.has_pending_retirements is False
        assert candidate.ownership_state == "disposed"
        assert attempts == 2

    asyncio.run(scenario())
