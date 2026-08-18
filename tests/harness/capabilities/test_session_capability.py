from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import pytest

from loushang.harness.capabilities import (
    CapabilityBundleValue,
    CapabilityDependencyBinding,
    CapabilityFacetBinding,
    CapabilityGraphPlanningError,
    CapabilityGraphPlanRequest,
    CapabilityPack,
    RuntimeCapabilityGraphBinder,
    RuntimeCapabilityGraphPlanner,
    RuntimeCapabilityGraphRuntime,
    standard_capability_composition_plan,
)
from loushang.harness.capabilities.prompt import PromptSection
from loushang.harness.capabilities.resources_contracts import (
    PROMPT_SECTIONS_FACET,
    RESOURCES_CAPABILITY_DEFINITION,
    RESOURCES_PROMPT_REQUIREMENT,
)
from loushang.harness.capabilities.resources_provider import (
    resources_capability_provider_binding,
)
from loushang.harness.capabilities.session_contracts import (
    SESSION_CAPABILITY_DEFINITION,
    SESSION_RESOURCE_COMPOSITION_REQUIREMENT,
    SESSION_SIDE_QUESTION_REQUIREMENT,
    SESSION_TRANSCRIPT_REQUIREMENT,
    SESSION_WORKSPACE_PROCESS_REQUIREMENT,
    SESSION_WORKSPACE_TOOL_REQUIREMENT,
)
from loushang.harness.capabilities.workspace_contracts import (
    WORKSPACE_CAPABILITY_DEFINITION,
)
from loushang.harness.capabilities.workspace_provider import (
    workspace_capability_provider_binding,
)
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.runtime import (
    ResolvedRuntimeProfile,
    RuntimeProfileResolver,
    SideQuestionAnswer,
)
from loushang.harness.session.legacy_side_question import bind_legacy_side_question
from loushang.harness.session.session_capability_consumer import (
    SessionResourceCompositionCapabilityConsumer,
    SessionSideQuestionCapabilityConsumer,
    SessionTranscriptCapabilityConsumer,
    SessionWorkspaceProcessCapabilityConsumer,
    SessionWorkspaceToolCapabilityConsumer,
)
from loushang.harness.session.session_capability_provider import (
    _ResourceCompositionFacet,
    _WorkspaceProcessFacet,
    _WorkspaceToolFacet,
    session_capability_provider_binding,
)
from loushang.harness.workspace.operations import LOCAL_TOOL_OPERATIONS
from loushang.harness.workspace.process import ProcessLaunchRequest


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _candidate():  # type: ignore[no-untyped-def]
    profile = _profile()
    return bind_legacy_side_question(profile)


def _profile():  # type: ignore[no-untyped-def]
    return RuntimeProfileResolver().resolve(
        standard_capability_composition_plan(product_id="research")
    )


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


def _graph_inputs(  # type: ignore[no-untyped-def]
    binding,
    resources=None,
    workspace=None,
):
    resources = resources or resources_capability_provider_binding(
        profile=_profile(), scope_instance_id="session:research"
    )
    plan = RuntimeCapabilityGraphPlanner().plan(
        CapabilityGraphPlanRequest(
            product_id="research",
            roots=(SESSION_CAPABILITY_DEFINITION.capability_id,),
            definitions=(
                RESOURCES_CAPABILITY_DEFINITION,
                SESSION_CAPABILITY_DEFINITION,
                *((WORKSPACE_CAPABILITY_DEFINITION,) if workspace else ()),
            ),
            providers=(
                resources.provider,
                binding.provider,
                *((workspace.provider,) if workspace else ()),
            ),
        )
    )
    return plan, (resources, binding, *((workspace,) if workspace else ()))


class _WorkspaceLauncher:
    def __init__(self) -> None:
        self.calls = 0
        self.handle = object()

    async def start(  # type: ignore[no-untyped-def]
        self,
        request,
        *,
        correlation_id,
        signal=None,
    ):
        del request, correlation_id, signal
        self.calls += 1
        return self.handle


def test_session_binding_signature_includes_resources_dependency() -> None:
    async def mounted_signatures(resource_marker: str):
        side = _candidate()
        transcript = _TranscriptCandidate()
        session = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=side,
            staged_transcript=transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        resources = resources_capability_provider_binding(
            profile=_profile(),
            scope_instance_id="session:research",
        )
        resources = replace(
            resources,
            binding_input_fingerprint=_sha(resource_marker),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(runtime, *_graph_inputs(session, resources))
        assert runtime.snapshot is not None
        signatures = {
            node.capability_id: node.binding_signature
            for node in runtime.snapshot.nodes
        }
        await binder.dispose(runtime)
        return session.binding_input_fingerprint, signatures

    first_input, first = asyncio.run(mounted_signatures("resource-one"))
    second_input, second = asyncio.run(mounted_signatures("resource-two"))

    assert first_input == second_input
    assert first["harness.resources"] != second["harness.resources"]
    assert first["harness.session"] != second["harness.session"]


def test_session_binding_signature_includes_optional_workspace_dependency() -> None:
    async def mounted_signatures(workspace_marker: str):
        session = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=_candidate(),
            staged_transcript=_TranscriptCandidate(),
            bind_provider=lambda _factory: _Provider(),
        )
        workspace = workspace_capability_provider_binding(
            operations=LOCAL_TOOL_OPERATIONS,
            process_launcher=_WorkspaceLauncher(),
            scope_instance_id="workspace:research",
            binding_input_fingerprint=_sha(workspace_marker),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(
            runtime,
            *_graph_inputs(session, workspace=workspace),
        )
        assert runtime.snapshot is not None
        signatures = {
            node.capability_id: node.binding_signature
            for node in runtime.snapshot.nodes
        }
        await binder.dispose(runtime)
        return session.binding_input_fingerprint, signatures

    first_input, first = asyncio.run(mounted_signatures("workspace-one"))
    second_input, second = asyncio.run(mounted_signatures("workspace-two"))

    assert first_input == second_input
    assert first["harness.workspace"] != second["harness.workspace"]
    assert first["harness.session"] != second["harness.session"]


def test_session_plan_requires_resources_before_candidate_construction() -> None:
    side = _candidate()
    transcript = _TranscriptCandidate()
    binding = session_capability_provider_binding(
        scope_instance_id="session:research",
        staged_side_question=side,
        staged_transcript=transcript,
        bind_provider=lambda _factory: _Provider(),
    )
    try:
        with pytest.raises(CapabilityGraphPlanningError) as caught:
            RuntimeCapabilityGraphPlanner().plan(
                CapabilityGraphPlanRequest(
                    product_id="research",
                    roots=(SESSION_CAPABILITY_DEFINITION.capability_id,),
                    definitions=(SESSION_CAPABILITY_DEFINITION,),
                    providers=(binding.provider,),
                )
            )

        assert tuple(item.code for item in caught.value.diagnostics) == (
            "unknown_capability",
        )
        assert side.ownership_state == "root_owned"
        assert transcript.ownership_state == "root_owned"
    finally:
        side.dispose()
        asyncio.run(transcript.dispose_root_owned())


def test_session_resource_facet_rejects_a_narrower_dependency_view() -> None:
    dependency = CapabilityDependencyBinding(
        RESOURCES_PROMPT_REQUIREMENT,
        CapabilityBundleValue(
            (CapabilityFacetBinding(PROMPT_SECTIONS_FACET, object()),)
        ),
    )

    with pytest.raises(ValueError, match="wrong dependency view"):
        _ResourceCompositionFacet(dependency)
    with pytest.raises(ValueError, match="wrong dependency view"):
        _WorkspaceToolFacet(dependency)
    with pytest.raises(ValueError, match="wrong dependency view"):
        _WorkspaceProcessFacet(dependency)


class _Provider:
    def __init__(self) -> None:
        self.cancel_calls = 0

    async def ask(self, question, *, on_update=None):  # type: ignore[no-untyped-def]
        if on_update is not None:
            await on_update("update")
        return SideQuestionAnswer(text=question)

    def cancel(self) -> None:
        self.cancel_calls += 1


def test_session_side_question_candidate_transfers_to_one_generation_lease(
    tmp_path,
) -> None:
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

        await binder.bind(runtime, *_graph_inputs(binding))
        consumer = SessionSideQuestionCapabilityConsumer(
            runtime.capture(SESSION_SIDE_QUESTION_REQUIREMENT)
        )
        transcript_consumer = SessionTranscriptCapabilityConsumer(
            runtime.capture(SESSION_TRANSCRIPT_REQUIREMENT)
        )
        resource_consumer = SessionResourceCompositionCapabilityConsumer(
            runtime.capture(SESSION_RESOURCE_COMPOSITION_REQUIREMENT)
        )
        workspace_tools = SessionWorkspaceToolCapabilityConsumer(
            runtime.capture(SESSION_WORKSPACE_TOOL_REQUIREMENT)
        )
        workspace_process = SessionWorkspaceProcessCapabilityConsumer(
            runtime.capture(SESSION_WORKSPACE_PROCESS_REQUIREMENT)
        )

        assert candidate.ownership_state == "graph_owned"
        assert transcript.ownership_state == "graph_owned"
        assert transcript_consumer.facets.is_current is True
        assert (await consumer.ask("status?")).text == "status?"
        assert runtime.snapshot is not None
        assert SESSION_CAPABILITY_DEFINITION.phase == "final"
        bundle = ResourceBundle(cwd=tmp_path)
        activated_bundle = resource_consumer.apply_skill_activation(bundle, ())
        assert resource_consumer.activate(activated_bundle).active_skills() == ()
        assert (
            resource_consumer.compose_prompt((PromptSection("base", "Base"),)).text
            == "Base"
        )
        assert resource_consumer.compose_tools(
            (CapabilityPack("tools", "product", ("tool",)),)
        ).items == ("tool",)
        assert resource_consumer.compose_commands(
            (CapabilityPack("commands", "product", ("command",)),)
        ).items == ("command",)
        assert SESSION_CAPABILITY_DEFINITION.contract_version == 4
        assert SESSION_SIDE_QUESTION_REQUIREMENT.compatible_contract.accepts(1)
        assert SESSION_SIDE_QUESTION_REQUIREMENT.compatible_contract.accepts(2)
        assert SESSION_SIDE_QUESTION_REQUIREMENT.compatible_contract.accepts(3)
        assert SESSION_SIDE_QUESTION_REQUIREMENT.compatible_contract.accepts(4)
        assert SESSION_TRANSCRIPT_REQUIREMENT.compatible_contract.accepts(2)
        assert SESSION_TRANSCRIPT_REQUIREMENT.compatible_contract.accepts(3)
        assert SESSION_TRANSCRIPT_REQUIREMENT.compatible_contract.accepts(4)
        assert SESSION_RESOURCE_COMPOSITION_REQUIREMENT.compatible_contract.accepts(3)
        assert SESSION_RESOURCE_COMPOSITION_REQUIREMENT.compatible_contract.accepts(4)
        assert tuple(node.capability_id for node in runtime.snapshot.nodes) == (
            "harness.resources",
            "harness.session",
        )
        session_node = runtime.snapshot.nodes[1]
        assert tuple(
            requirement.capability_id for requirement in session_node.requirements
        ) == ("harness.resources",)
        with pytest.raises(RuntimeError, match="not available"):
            workspace_tools.apply().read_operations.read_bytes(tmp_path / "missing")  # type: ignore[union-attr]
        with pytest.raises(RuntimeError, match="not available"):
            await workspace_process.process_launcher.start(
                ProcessLaunchRequest(
                    command=("never-start",),
                    cwd=str(tmp_path),
                    effective_environment=(),
                ),
                correlation_id="generic-no-workspace",
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
        with pytest.raises(RuntimeError, match="disposed"):
            resource_consumer.compose_prompt((PromptSection("base", "Base"),))

    asyncio.run(scenario())


def test_session_workspace_dependency_is_optional_and_lease_scoped(tmp_path) -> None:
    async def scenario() -> None:
        candidate = _candidate()
        transcript = _TranscriptCandidate()
        session_binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=candidate,
            staged_transcript=transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        launcher = _WorkspaceLauncher()
        workspace_binding = workspace_capability_provider_binding(
            operations=LOCAL_TOOL_OPERATIONS,
            process_launcher=launcher,
            scope_instance_id="workspace:research",
            binding_input_fingerprint=_sha("workspace"),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()

        await binder.bind(
            runtime,
            *_graph_inputs(session_binding, workspace=workspace_binding),
        )
        assert runtime.snapshot is not None
        assert runtime.snapshot.roots == ("harness.session",)
        assert tuple(node.capability_id for node in runtime.snapshot.nodes) == (
            "harness.resources",
            "harness.workspace",
            "harness.session",
        )
        session_node = runtime.snapshot.nodes[-1]
        assert tuple(
            requirement.capability_id for requirement in session_node.requirements
        ) == ("harness.resources", "harness.workspace")

        tools = SessionWorkspaceToolCapabilityConsumer(
            runtime.capture(SESSION_WORKSPACE_TOOL_REQUIREMENT)
        )
        process = SessionWorkspaceProcessCapabilityConsumer(
            runtime.capture(SESSION_WORKSPACE_PROCESS_REQUIREMENT)
        )
        source = tmp_path / "source.txt"
        source.write_text("workspace-data", encoding="utf-8")
        read_operations = tools.apply().read_operations
        assert read_operations is not None
        assert read_operations.read_bytes(source) == b"workspace-data"
        process_launcher = process.process_launcher
        handle = await process_launcher.start(
            ProcessLaunchRequest(
                command=("fake",),
                cwd=str(tmp_path),
                effective_environment=(),
            ),
            correlation_id="workspace-process",
        )
        assert handle is launcher.handle
        assert launcher.calls == 1

        await binder.dispose(runtime)

        with pytest.raises(RuntimeError, match="disposed"):
            read_operations.read_bytes(source)
        with pytest.raises(RuntimeError, match="disposed"):
            await process_launcher.start(
                ProcessLaunchRequest(
                    command=("stale",),
                    cwd=str(tmp_path),
                    effective_environment=(),
                ),
                correlation_id="stale-process",
            )
        assert launcher.calls == 1

    asyncio.run(scenario())


def test_replaced_session_invalidates_workspace_proxies_when_workspace_is_reused(
    tmp_path,
) -> None:
    async def scenario() -> None:
        first_side = _candidate()
        first_transcript = _TranscriptCandidate(profile_product_id="research-one")
        first_session = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=first_side,
            staged_transcript=first_transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        resources = resources_capability_provider_binding(
            profile=_profile(),
            scope_instance_id="session:research",
        )
        workspace = workspace_capability_provider_binding(
            operations=LOCAL_TOOL_OPERATIONS,
            process_launcher=_WorkspaceLauncher(),
            scope_instance_id="workspace:research",
            binding_input_fingerprint=_sha("stable-workspace"),
        )
        runtime = RuntimeCapabilityGraphRuntime(
            product_id="research",
            runtime_id="research-session",
            profile_fingerprint=_sha("profile"),
        )
        binder = RuntimeCapabilityGraphBinder()
        await binder.bind(
            runtime,
            *_graph_inputs(first_session, resources, workspace),
        )
        first_tools = SessionWorkspaceToolCapabilityConsumer(
            runtime.capture(SESSION_WORKSPACE_TOOL_REQUIREMENT)
        )
        cached_read = first_tools.apply().read_operations
        assert cached_read is not None
        source = tmp_path / "source.txt"
        source.write_text("current", encoding="utf-8")
        assert cached_read.read_bytes(source) == b"current"

        second_side = _candidate()
        second_transcript = _TranscriptCandidate(profile_product_id="research-two")
        second_session = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=second_side,
            staged_transcript=second_transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        result = await binder.bind(
            runtime,
            *_graph_inputs(second_session, resources, workspace),
        )

        assert result.reused_capability_ids == (
            "harness.resources",
            "harness.workspace",
        )
        assert result.created_capability_ids == ("harness.session",)
        assert first_side.ownership_state == "disposed"
        assert first_transcript.ownership_state == "disposed"
        assert second_side.ownership_state == "graph_owned"
        assert second_transcript.ownership_state == "graph_owned"
        with pytest.raises(RuntimeError, match="stale"):
            cached_read.read_bytes(source)

        second_tools = SessionWorkspaceToolCapabilityConsumer(
            runtime.capture(SESSION_WORKSPACE_TOOL_REQUIREMENT)
        )
        replacement_read = second_tools.apply().read_operations
        assert replacement_read is not None
        assert replacement_read.read_bytes(source) == b"current"

        await binder.dispose(runtime)
        assert second_side.ownership_state == "disposed"
        assert second_transcript.ownership_state == "disposed"

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
        await binder.bind(runtime, *_graph_inputs(first_binding))

        rejected_candidate = _candidate()
        rejected_transcript = _TranscriptCandidate()
        rejected_binding = session_capability_provider_binding(
            scope_instance_id="session:research",
            staged_side_question=rejected_candidate,
            staged_transcript=rejected_transcript,
            bind_provider=lambda _factory: _Provider(),
        )
        result = await binder.bind(runtime, *_graph_inputs(rejected_binding))

        assert result.reused_capability_ids == (
            "harness.resources",
            "harness.session",
        )
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
        await binder.bind(runtime, *_graph_inputs(binding))
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
                *_graph_inputs(binding),
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
            await binder.bind(runtime, *_graph_inputs(binding))

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
                *_graph_inputs(binding),
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
                *_graph_inputs(binding),
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
        await binder.bind(runtime, *_graph_inputs(binding))

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
        await binder.bind(runtime, *_graph_inputs(binding))

        assert await binder.dispose(runtime) == ("provider_retirement_failed",)
        assert side.ownership_state == "disposed"
        assert transcript.ownership_state == "graph_owned"
        assert await binder.dispose(runtime) == ()

        assert transcript.ownership_state == "disposed"
        assert transcript.dispose_calls == 2
        assert runtime.has_pending_retirements is False

    asyncio.run(scenario())
