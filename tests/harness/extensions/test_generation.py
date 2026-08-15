from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from loushang.harness.extensions.agent import ExtensionRunner
from loushang.harness.extensions.context import ExtensionRuntimeBindings
from loushang.harness.extensions.types import LoadedExtension
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.runtime.registration import (
    RegistrationDisposalResult,
    RegistrationIdentity,
    RegistrationLease,
    RegistrationOwner,
)
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.execution import direct_execution


async def _ignore_async(*_args: object, **_kwargs: object) -> None:
    return None


def _tool(name: str, marker: str) -> ToolDefinition:
    async def execute(
        tool_call_id: str,
        arguments: dict[str, object],
        signal: object | None,
        on_update: object | None,
    ) -> object:
        del tool_call_id, arguments, signal, on_update
        return marker

    return ToolDefinition(
        name=name,
        label=name,
        description=marker,
        parameters={},
        execution=direct_execution(execute),  # type: ignore[arg-type]
    )


def _bindings(
    bind_tool: Callable[
        [object, RegistrationOwner | str, object | None], RegistrationLease
    ],
) -> ExtensionRuntimeBindings:
    return ExtensionRuntimeBindings(
        cwd="/tmp/project",
        get_active_tool_names=lambda: ["lookup"],
        get_model_selection=lambda: None,
        set_active_tools=_ignore_async,
        set_model=_ignore_async,
        request_resource_refresh=lambda: None,
        shutdown=lambda: None,
        record_diagnostic=lambda _diagnostic: None,
        bind_tool=bind_tool,
        stage_tool=bind_tool,
    )


def test_failed_candidate_binding_restores_the_old_extension_generation() -> None:
    layers: list[tuple[str, str]] = []
    disposals: list[str] = []
    fail_marker = "new-second"

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        if value.description == fail_marker:
            raise RuntimeError("candidate bind failed")
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )
        layers.append((identity.registration_id, value.description))

        def dispose() -> RegistrationDisposalResult:
            for index, entry in enumerate(layers):
                if entry[0] == identity.registration_id:
                    layers.pop(index)
                    disposals.append(value.description)
                    return RegistrationDisposalResult(state="removed")
            return RegistrationDisposalResult(state="already_removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=dispose)

    old = LoadedExtension(
        name="review",
        source_path=Path("/tmp/review.py"),
        tool_definitions=[_tool("lookup", "old")],
    )
    candidate_extension = LoadedExtension(
        name="review",
        source_path=Path("/tmp/review.py"),
        tool_definitions=[
            _tool("lookup", "new-first"),
            _tool("inspect", fail_marker),
        ],
    )
    runtime = ExtensionRunner([old])
    bindings = _bindings(bind_tool)

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        old_context = runtime.create_command_context()
        candidate = runtime.prepare_generation([candidate_extension])
        with pytest.raises(RuntimeError, match="candidate bind failed"):
            await candidate.activate(bindings)

        assert runtime.generation == 1
        assert old_context.cwd == "/tmp/project"
        assert [marker for _, marker in layers] == ["old"]

    asyncio.run(scenario())

    assert disposals == ["new-first"]


def test_published_extension_generation_retires_old_registrations_exactly_once() -> (
    None
):
    layers: list[tuple[str, str]] = []
    disposal_counts: dict[str, int] = {}

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )
        layers.append((identity.registration_id, value.description))

        def dispose() -> RegistrationDisposalResult:
            disposal_counts[value.description] = (
                disposal_counts.get(value.description, 0) + 1
            )
            for index, entry in enumerate(layers):
                if entry[0] == identity.registration_id:
                    layers.pop(index)
                    return RegistrationDisposalResult(state="removed")
            return RegistrationDisposalResult(state="already_removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=dispose)

    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[_tool("lookup", "old")],
            )
        ]
    )
    bindings = _bindings(bind_tool)
    committed: list[ResourceBundle] = []

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        old_context = runtime.create_command_context()
        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/review.py"),
                    tool_definitions=[_tool("lookup", "new")],
                )
            ]
        )
        bundle = ResourceBundle(cwd=Path("/tmp/project"))
        await candidate.activate(bindings)
        retirement = candidate.publish(lambda: committed.append(bundle))

        assert runtime.generation == 2
        assert [marker for _, marker in layers] == ["old", "new"]
        with pytest.raises(RuntimeError, match="stale"):
            _ = old_context.cwd

        await retirement.retire()
        await retirement.retire()

        assert [marker for _, marker in layers] == ["new"]

    asyncio.run(scenario())

    assert committed == [ResourceBundle(cwd=Path("/tmp/project"))]
    assert disposal_counts == {"old": 1}


def test_cancelled_candidate_binding_keeps_old_generation_and_rolls_back() -> None:
    layers: list[tuple[str, str]] = []
    disposals: list[str] = []

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )
        layers.append((identity.registration_id, value.description))

        def dispose() -> RegistrationDisposalResult:
            disposals.append(value.description)
            layers[:] = [
                entry
                for entry in layers
                if entry[0] != identity.registration_id
            ]
            return RegistrationDisposalResult(state="removed")

        lease = RegistrationLease(owner=owner, identity=identity, dispose=dispose)
        if value.description == "new-second":
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
        return lease

    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[_tool("lookup", "old")],
            )
        ]
    )
    bindings = _bindings(bind_tool)

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        old_context = runtime.create_command_context()
        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/review.py"),
                    tool_definitions=[
                        _tool("lookup", "new-first"),
                        _tool("inspect", "new-second"),
                    ],
                )
            ]
        )

        with pytest.raises(asyncio.CancelledError):
            await candidate.activate(bindings)

        assert runtime.generation == 1
        assert old_context.cwd == "/tmp/project"
        assert [marker for _, marker in layers] == ["old"]

    asyncio.run(scenario())

    assert disposals == ["new-second", "new-first"]


def test_failed_generation_publication_restores_old_runtime_and_context() -> None:
    layers: list[tuple[str, str]] = []

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )
        layers.append((identity.registration_id, value.description))

        def dispose() -> RegistrationDisposalResult:
            layers[:] = [
                entry
                for entry in layers
                if entry[0] != identity.registration_id
            ]
            return RegistrationDisposalResult(state="removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=dispose)

    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[_tool("lookup", "old")],
            )
        ]
    )
    bindings = _bindings(bind_tool)

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        old_context = runtime.create_command_context()
        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/review.py"),
                    tool_definitions=[_tool("lookup", "new")],
                )
            ]
        )
        await candidate.activate(bindings)

        def fail_commit() -> None:
            raise RuntimeError("resource commit failed")

        with pytest.raises(RuntimeError, match="resource commit failed"):
            candidate.publish(fail_commit)
        await candidate.rollback()

        assert runtime.generation == 1
        assert old_context.cwd == "/tmp/project"
        assert [marker for _, marker in layers] == ["old"]

    asyncio.run(scenario())


def test_cancelled_retirement_joins_cleanup_and_keeps_new_generation() -> None:
    layers: list[tuple[str, str]] = []
    old_disposal_started = asyncio.Event()
    release_old_disposal = asyncio.Event()
    old_disposals = 0

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )
        layers.append((identity.registration_id, value.description))

        async def dispose() -> RegistrationDisposalResult:
            nonlocal old_disposals
            if value.description == "old":
                old_disposals += 1
                old_disposal_started.set()
                await release_old_disposal.wait()
            layers[:] = [
                entry
                for entry in layers
                if entry[0] != identity.registration_id
            ]
            return RegistrationDisposalResult(state="removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=dispose)

    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[_tool("lookup", "old")],
            )
        ]
    )
    bindings = _bindings(bind_tool)

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/review.py"),
                    tool_definitions=[_tool("lookup", "new")],
                )
            ]
        )
        await candidate.activate(bindings)
        retirement = candidate.publish(lambda: None)
        task = asyncio.create_task(retirement.retire())
        await old_disposal_started.wait()
        task.cancel()
        release_old_disposal.set()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert runtime.generation == 2
        assert runtime.create_command_context().cwd == "/tmp/project"
        assert [marker for _, marker in layers] == ["new"]

    asyncio.run(scenario())

    assert old_disposals == 1


def test_initial_generation_binding_failure_never_publishes_partial_tools() -> None:
    from loushang.harness.tools.core import ToolRegistry

    registry = ToolRegistry()
    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[
                    _tool("first", "first"),
                    _tool("second", "second"),
                ],
            )
        ]
    )

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        assert isinstance(owner, RegistrationOwner)
        if isinstance(value, ToolDefinition) and value.name == "second":
            raise RuntimeError("second Tool failed")
        return registry.bind_tool(value, owner=owner, source_info=source_info)

    def stage_tool(
        value: object,
        owner: RegistrationOwner,
        source_info: object | None,
    ) -> RegistrationLease:
        if isinstance(value, ToolDefinition) and value.name == "second":
            raise RuntimeError("second Tool failed")
        return registry.stage_tool(value, owner=owner, source_info=source_info)

    bindings = _bindings(bind_tool)
    bindings.stage_tool = stage_tool

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="second Tool failed"):
            runner.bind_runtime(bindings)
        assert registry.list_definitions() == []
        await runner.dispose_runtime_generation()

    asyncio.run(scenario())


def test_prepare_generation_rejects_active_extension_or_api_identity_reuse() -> None:
    api = object()
    extension = LoadedExtension(
        name="review",
        source_path=Path("/tmp/review.py"),
        api=api,
    )
    runner = ExtensionRunner([extension])

    with pytest.raises(ValueError, match="active LoadedExtension or API"):
        runner.prepare_generation([extension])
    with pytest.raises(ValueError, match="active LoadedExtension or API"):
        runner.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/reloaded-review.py"),
                    api=api,
                )
            ]
        )


def test_runner_keeps_single_argument_runtime_api_compatibility() -> None:
    calls: list[object] = []

    class LegacyAPI:
        def bind_runtime_state(self, state: object) -> None:
            calls.append(state)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="legacy",
                source_path=Path("/tmp/legacy.py"),
                api=LegacyAPI(),
            )
        ]
    )
    runner.bind_runtime(_bindings(lambda *_args: pytest.fail("unexpected Tool bind")))

    assert len(calls) == 1


def test_candidate_cannot_publish_after_runtime_shutdown_begins() -> None:
    layers: list[str] = []
    old_disposal_started = asyncio.Event()
    release_old_disposal = asyncio.Event()

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        marker = value.description
        layers.append(marker)
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )

        async def dispose() -> RegistrationDisposalResult:
            if marker == "old":
                old_disposal_started.set()
                await release_old_disposal.wait()
            if marker in layers:
                layers.remove(marker)
            return RegistrationDisposalResult(state="removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=dispose)

    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[_tool("lookup", "old")],
            )
        ]
    )
    bindings = _bindings(bind_tool)

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/review.py"),
                    tool_definitions=[_tool("lookup", "new")],
                )
            ]
        )
        shutdown = asyncio.create_task(runtime.dispose_runtime_generation())
        await old_disposal_started.wait()

        async def publish_candidate() -> None:
            await candidate.activate(bindings)
            candidate.publish(lambda: None)

        publication = asyncio.create_task(publish_candidate())
        await asyncio.sleep(0)
        release_old_disposal.set()
        await shutdown
        with pytest.raises(RuntimeError, match="disposed"):
            await publication

        assert runtime.generation == 1
        assert layers == []

    asyncio.run(scenario())


def test_shutdown_retains_retryable_retired_generation_cleanup() -> None:
    layers: list[str] = []
    old_disposal_attempts = 0

    def bind_tool(
        value: object,
        owner: RegistrationOwner | str,
        source_info: object | None,
    ) -> RegistrationLease:
        del source_info
        assert isinstance(value, ToolDefinition)
        assert isinstance(owner, RegistrationOwner)
        marker = value.description
        layers.append(marker)
        identity = RegistrationIdentity.create(
            surface="review-tool",
            public_key=value.name,
        )

        def dispose() -> RegistrationDisposalResult:
            nonlocal old_disposal_attempts
            if marker == "old":
                old_disposal_attempts += 1
                if old_disposal_attempts < 3:
                    return RegistrationDisposalResult(state="failed_retryable")
            if marker in layers:
                layers.remove(marker)
            return RegistrationDisposalResult(state="removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=dispose)

    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="review",
                source_path=Path("/tmp/review.py"),
                tool_definitions=[_tool("lookup", "old")],
            )
        ]
    )
    bindings = _bindings(bind_tool)

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="review",
                    source_path=Path("/tmp/review.py"),
                    tool_definitions=[_tool("lookup", "new")],
                )
            ]
        )
        await candidate.activate(bindings)
        retirement = candidate.publish(lambda: None)
        first = await retirement.retire()
        assert first[0].has_failures

        await runtime.dispose_runtime_generation()
        await runtime.dispose_runtime_generation()

        assert old_disposal_attempts == 3
        assert layers == []

    asyncio.run(scenario())


def test_candidate_provider_removal_does_not_clobber_old_generation() -> None:
    from loushang.ai.model import Provider
    from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
    from loushang.harness.extensions.agent.api import ExtensionAPI
    from loushang.harness.model_catalog import ModelCatalog

    catalog = ModelCatalog(AiModelRegistry())
    old_api = ExtensionAPI(name="models", source_path=Path("/tmp/models.py"))
    old_api.register_provider("shared", {"name": "old"})
    runtime = ExtensionRunner(
        [
            LoadedExtension(
                name="models",
                source_path=Path("/tmp/models.py"),
                api=old_api,
            )
        ]
    )
    bindings = _bindings(lambda *_args: pytest.fail("unexpected Tool bind"))

    def provider(name: str, config: object) -> Provider:
        assert isinstance(config, dict)
        return Provider(id=name, name=str(config["name"]))

    bindings.bind_provider = lambda name, config, owner: catalog.bind_provider(
        provider(name, config),
        owner=owner,
    )
    bindings.stage_provider = lambda name, config, owner: catalog.stage_provider(
        provider(name, config),
        owner=owner,
    )
    bindings.bind_provider_removal = (
        lambda name, owner: catalog.bind_provider_removal(name, owner=owner)
    )
    bindings.stage_provider_removal = (
        lambda name, owner: catalog.stage_provider_removal(name, owner=owner)
    )
    bindings.unregister_provider = catalog.unregister_provider

    candidate_api = ExtensionAPI(
        name="models",
        source_path=Path("/tmp/reloaded-models.py"),
    )
    candidate_api.unregister_provider("shared")

    async def scenario() -> None:
        await runtime.activate_runtime_generation(bindings)
        assert catalog.ai_registry.get_provider("shared") == Provider(
            id="shared",
            name="old",
        )

        candidate = runtime.prepare_generation(
            [
                LoadedExtension(
                    name="models",
                    source_path=Path("/tmp/reloaded-models.py"),
                    api=candidate_api,
                )
            ]
        )
        await candidate.activate(bindings)
        assert catalog.ai_registry.get_provider("shared") is not None

        await candidate.rollback()
        restored = catalog.ai_registry.get_provider("shared")
        assert restored is not None
        assert restored.name == "old"
        await runtime.dispose_runtime_generation()

    asyncio.run(scenario())
