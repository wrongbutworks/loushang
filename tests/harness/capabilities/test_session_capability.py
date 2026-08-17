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
    SESSION_TRANSCRIPT_REQUIREMENT,
)
from loushang.harness.runtime import (
    ResolvedRuntimeProfile,
    RuntimeProfileResolver,
    SideQuestionAnswer,
)
from loushang.harness.session.legacy_side_question import bind_legacy_side_question
from loushang.harness.session.session_capability_consumer import (
    SessionSideQuestionCapabilityConsumer,
    SessionTranscriptCapabilityConsumer,
)
from loushang.harness.session.session_capability_provider import (
    session_capability_provider_binding,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _candidate():  # type: ignore[no-untyped-def]
    profile = RuntimeProfileResolver().resolve(
        standard_capability_composition_plan(product_id="research")
    )
    return bind_legacy_side_question(profile)


class _TranscriptCandidate:
    def __init__(
        self,
        *,
        fail_begin: bool = False,
        fail_commit: bool = False,
        fail_dispose_once: bool = False,
        profile_product_id: str = "research",
    ) -> None:
        self.ownership_state = "root_owned"
        self.runtime_profile_snapshot = ResolvedRuntimeProfile(
            product_id=profile_product_id,
            capabilities=(),
        ).snapshot()
        self.publish_calls = 0
        self.dispose_calls = 0
        self.events: list[str] = []
        self._fail_begin = fail_begin
        self._fail_commit = fail_commit
        self._fail_dispose_once = fail_dispose_once

    def _begin_graph_construction(self) -> None:
        assert self.ownership_state == "root_owned"
        if self._fail_begin:
            raise RuntimeError("transcript ownership begin failed")
        self.ownership_state = "graph_constructing"

    def _commit_graph_ownership(self) -> None:
        assert self.ownership_state == "graph_constructing"
        if self._fail_commit:
            raise RuntimeError("transcript ownership commit failed")
        self.ownership_state = "graph_owned"

    def _restore_root_ownership(self) -> None:
        assert self.ownership_state == "graph_constructing"
        self.ownership_state = "root_owned"

    def _rollback_unpublished_graph_ownership(self) -> None:
        assert self.ownership_state in {"graph_constructing", "graph_owned"}
        self.ownership_state = "root_owned"

    async def dispose_root_owned(self) -> None:
        assert self.ownership_state == "root_owned"
        self.dispose_calls += 1
        self.ownership_state = "disposed"

    async def publish_index_summary(self) -> None:
        self.publish_calls += 1
        self.events.append("index")

    async def _dispose_graph_owned(self) -> None:
        if self.ownership_state == "disposed":
            return
        assert self.ownership_state == "graph_owned"
        self.dispose_calls += 1
        self.events.append("release")
        if self._fail_dispose_once and self.dispose_calls == 1:
            raise RuntimeError("transient transcript cleanup failure")
        self.ownership_state = "disposed"


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
        transcript = _TranscriptCandidate()
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=candidate,
            staged_transcript=transcript,
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
        transcript_consumer = SessionTranscriptCapabilityConsumer(
            runtime.capture(SESSION_TRANSCRIPT_REQUIREMENT)
        )

        assert candidate.ownership_state == "graph_owned"
        assert transcript.ownership_state == "graph_owned"
        assert transcript_consumer.facets.is_current is True
        assert (await consumer.ask("status?")).text == "status?"
        assert runtime.snapshot is not None
        assert SESSION_CAPABILITY_DEFINITION.phase == "final"
        assert SESSION_CAPABILITY_DEFINITION.contract_version == 2
        assert SESSION_SIDE_QUESTION_REQUIREMENT.compatible_contract.accepts(1)
        assert SESSION_SIDE_QUESTION_REQUIREMENT.compatible_contract.accepts(2)
        assert SESSION_TRANSCRIPT_REQUIREMENT.compatible_contract.accepts(2)
        assert tuple(node.capability_id for node in runtime.snapshot.nodes) == (
            "harness.session",
        )

        await binder.dispose(runtime)

        assert candidate.ownership_state == "disposed"
        assert transcript.ownership_state == "disposed"
        assert transcript.publish_calls == 1
        assert transcript.dispose_calls == 1
        assert transcript.events == ["index", "release"]
        assert transcript_consumer.facets.is_current is False
        with pytest.raises(RuntimeError, match="disposed"):
            await consumer.ask("again")

    asyncio.run(scenario())


def test_session_side_question_reuse_leaves_new_candidate_root_owned() -> None:
    async def scenario() -> None:
        first_candidate = _candidate()
        first_transcript = _TranscriptCandidate()
        first_binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=first_candidate,
            staged_transcript=first_transcript,
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
        rejected_transcript = _TranscriptCandidate()
        rejected_binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=rejected_candidate,
            staged_transcript=rejected_transcript,
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
        transcript = _TranscriptCandidate()
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=candidate,
            staged_transcript=transcript,
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
    fourth_candidate = _candidate()
    try:
        first = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=first_candidate,
            staged_transcript=_TranscriptCandidate(),
            bind_provider=lambda _factory: _Provider(),
        )
        second = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=second_candidate,
            staged_transcript=_TranscriptCandidate(),
            bind_provider=lambda _factory: _Provider(),
        )
        other_scope = session_capability_provider_binding(
            scope_instance_id="session:other",
            staged_side_question=third_candidate,
            staged_transcript=_TranscriptCandidate(),
            bind_provider=lambda _factory: _Provider(),
        )
        other_transcript = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=fourth_candidate,
            staged_transcript=_TranscriptCandidate(
                profile_product_id="marker-secret-profile"
            ),
            bind_provider=lambda _factory: _Provider(),
        )

        assert first.binding_input_fingerprint == second.binding_input_fingerprint
        assert first.binding_input_fingerprint != other_scope.binding_input_fingerprint
        assert first.binding_input_fingerprint != (
            other_transcript.binding_input_fingerprint
        )
        assert "marker-secret-profile" not in repr(other_transcript)
    finally:
        first_candidate.dispose()
        second_candidate.dispose()
        third_candidate.dispose()
        fourth_candidate.dispose()


def test_session_side_question_construction_failure_restores_root_owner() -> None:
    async def scenario() -> None:
        candidate = _candidate()

        def fail(_factory):  # type: ignore[no-untyped-def]
            raise RuntimeError("cannot bind side-question Provider")

        transcript = _TranscriptCandidate()
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=candidate,
            staged_transcript=transcript,
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


def test_session_combined_provider_rolls_back_a_partial_ownership_commit() -> None:
    async def scenario() -> None:
        side = _candidate()
        transcript = _TranscriptCandidate(fail_commit=True)
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=side,
            staged_transcript=transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()

        with pytest.raises(RuntimeError, match="provider_construction_failed"):
            await binder.bind(runtime, _plan(binding), (binding,))

        assert side.ownership_state == "root_owned"
        assert transcript.ownership_state == "root_owned"
        assert runtime.snapshot is None
        assert runtime.has_pending_retirements is False
        assert await binder.dispose(runtime) == ()
        side.dispose()
        await transcript.dispose_root_owned()
        assert side.ownership_state == "disposed"
        assert transcript.ownership_state == "disposed"
        assert transcript.dispose_calls == 1

    asyncio.run(scenario())


def test_session_combined_provider_rolls_back_a_partial_ownership_begin() -> None:
    async def scenario() -> None:
        side = _candidate()
        transcript = _TranscriptCandidate(fail_begin=True)
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=side,
            staged_transcript=transcript,
            bind_provider=lambda _factory: _Provider(),
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

        assert side.ownership_state == "root_owned"
        assert transcript.ownership_state == "root_owned"
        assert runtime.snapshot is None
        assert runtime.has_pending_retirements is False
        side.dispose()
        await transcript.dispose_root_owned()

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
        transcript = _TranscriptCandidate()
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=candidate,
            staged_transcript=transcript,
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
        transcript = _TranscriptCandidate()
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=candidate,
            staged_transcript=transcript,
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


def test_session_graph_retries_transcript_release_without_reopening_side_owner() -> (
    None
):
    async def scenario() -> None:
        side = _candidate()
        transcript = _TranscriptCandidate(fail_dispose_once=True)
        binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=side,
            staged_transcript=transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(runtime, _plan(binding), (binding,))

        assert await binder.dispose(runtime) == ("provider_retirement_failed",)
        assert side.ownership_state == "disposed"
        assert transcript.ownership_state == "graph_owned"
        assert await binder.dispose(runtime) == ()

        assert transcript.ownership_state == "disposed"
        assert transcript.dispose_calls == 2
        assert runtime.has_pending_retirements is False

    asyncio.run(scenario())
