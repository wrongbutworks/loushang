from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import pytest

from loushang.harness.config.activation import (
    ConfigActivationRuntime,
    ConfigActivationStep,
)


@dataclass(frozen=True)
class _ResearchConfig:
    source_revision: str = "v1"
    index_profile: str = "balanced"
    renderer: str = "markdown"


@dataclass
class _ResearchContext:
    calls: list[object]


def _statuses(report: object) -> dict[str, str]:
    return {result.step: result.status for result in report.results}  # type: ignore[attr-defined]


def test_activation_uses_stable_topological_order() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)
    config = _ResearchConfig()
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "tail",
                select=lambda value: value.renderer,
                apply=lambda _value, state: state.calls.append("tail"),
                depends_on=("base",),
            ),
            ConfigActivationStep(
                "left",
                select=lambda value: value.index_profile,
                apply=lambda _value, state: state.calls.append("left"),
            ),
            ConfigActivationStep(
                "right",
                select=lambda value: value.index_profile,
                apply=lambda _value, state: state.calls.append("right"),
            ),
            ConfigActivationStep(
                "base",
                select=lambda value: value.source_revision,
                apply=lambda _value, state: state.calls.append("base"),
            ),
        )
    )

    report = runtime.start(config, context)

    assert calls == ["left", "right", "base", "tail"]
    assert report.operation == "start"
    assert report.revision >= 1
    assert report.ok is True
    assert _statuses(report) == {
        "left": "applied",
        "right": "applied",
        "base": "applied",
        "tail": "applied",
    }
    assert report.failures == ()
    assert report.raise_for_failure() is None


@pytest.mark.parametrize(
    ("steps", "message"),
    (
        (
            (
                ConfigActivationStep(
                    "source", lambda value: value, lambda _value, _context: None
                ),
                ConfigActivationStep(
                    "source", lambda value: value, lambda _value, _context: None
                ),
            ),
            "[Dd]uplicate.*source",
        ),
        (
            (
                ConfigActivationStep(
                    "index",
                    lambda value: value,
                    lambda _value, _context: None,
                    depends_on=("missing",),
                ),
            ),
            "missing.*index|index.*missing",
        ),
        (
            (
                ConfigActivationStep(
                    "source",
                    lambda value: value,
                    lambda _value, _context: None,
                    depends_on=("index",),
                ),
                ConfigActivationStep(
                    "index",
                    lambda value: value,
                    lambda _value, _context: None,
                    depends_on=("source",),
                ),
            ),
            "cycle",
        ),
    ),
)
def test_activation_rejects_invalid_dependency_graphs(
    steps: tuple[ConfigActivationStep, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ConfigActivationRuntime(steps)


def test_refresh_skips_unchanged_steps_and_cascades_changed_dependencies() -> None:
    calls: list[tuple[str, str]] = []
    context = _ResearchContext(calls)
    initial = _ResearchConfig()
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                select=lambda value: value.source_revision,
                apply=lambda value, state: state.calls.append(("source", value)),
            ),
            ConfigActivationStep(
                "index",
                select=lambda value: value.index_profile,
                apply=lambda value, state: state.calls.append(("index", value)),
                depends_on=("source",),
                cascade=False,
            ),
            ConfigActivationStep(
                "renderer",
                select=lambda value: value.renderer,
                apply=lambda value, state: state.calls.append(("renderer", value)),
                depends_on=("index",),
            ),
        )
    )
    started = runtime.start(initial, context)
    calls.clear()

    unchanged = runtime.refresh(initial, context)
    changed = runtime.refresh(replace(initial, source_revision="v2"), context)
    forced = runtime.refresh(
        replace(initial, source_revision="v2"),
        context,
        force=("renderer",),
    )

    assert started.revision < unchanged.revision < changed.revision < forced.revision
    assert unchanged.operation == changed.operation == forced.operation == "refresh"
    assert _statuses(unchanged) == {
        "source": "skipped",
        "index": "skipped",
        "renderer": "skipped",
    }
    assert _statuses(changed) == {
        "source": "applied",
        "index": "applied",
        "renderer": "skipped",
    }
    assert _statuses(forced) == {
        "source": "skipped",
        "index": "skipped",
        "renderer": "applied",
    }
    assert calls == [
        ("source", "v2"),
        ("index", "balanced"),
        ("renderer", "markdown"),
    ]


def test_refresh_always_step_runs_when_selection_is_unchanged() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)
    config = _ResearchConfig()
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "telemetry",
                select=lambda value: value.source_revision,
                apply=lambda value, state: state.calls.append(value),
                refresh="always",
            ),
        )
    )

    runtime.start(config, context)
    report = runtime.refresh(config, context)

    assert calls == ["v1", "v1"]
    assert _statuses(report) == {"telemetry": "applied"}


def test_failed_cascade_refresh_is_retried_without_another_dependency_change() -> None:
    child_attempts = 0

    def apply_child(_value: object, _context: _ResearchContext) -> None:
        nonlocal child_attempts
        child_attempts += 1
        if child_attempts == 2:
            raise RuntimeError("index unavailable")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value.source_revision,
                lambda _value, _context: None,
            ),
            ConfigActivationStep(
                "index",
                lambda value: value.index_profile,
                apply_child,
                depends_on=("source",),
            ),
        )
    )
    context = _ResearchContext([])
    runtime.start(_ResearchConfig(), context)

    failed = runtime.refresh(
        _ResearchConfig(source_revision="v2"),
        context,
    )
    retried = runtime.refresh(
        _ResearchConfig(source_revision="v2"),
        context,
    )

    assert _statuses(failed) == {"source": "applied", "index": "failed"}
    assert _statuses(retried) == {"source": "skipped", "index": "applied"}
    assert child_attempts == 3


def test_continue_failure_blocks_dependents_but_runs_independent_steps() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)

    def fail(_value: object, state: _ResearchContext) -> None:
        state.calls.append("broken")
        raise RuntimeError("index unavailable")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, state: state.calls.append("source"),
            ),
            ConfigActivationStep(
                "index",
                lambda value: value,
                fail,
                depends_on=("source",),
                failure_mode="continue",
            ),
            ConfigActivationStep(
                "search",
                lambda value: value,
                lambda _value, state: state.calls.append("search"),
                depends_on=("index",),
            ),
            ConfigActivationStep(
                "renderer",
                lambda value: value,
                lambda _value, state: state.calls.append("renderer"),
            ),
        )
    )

    report = runtime.start(_ResearchConfig(), context)

    assert calls == ["source", "renderer", "broken"]
    assert _statuses(report) == {
        "source": "applied",
        "index": "failed",
        "search": "blocked",
        "renderer": "applied",
    }
    assert report.ok is False
    assert len(report.failures) == 1
    assert report.failures[0].step == "index"
    assert isinstance(report.failures[0].error, RuntimeError)
    with pytest.raises(RuntimeError, match="index unavailable"):
        report.raise_for_failure()


def test_stop_failure_blocks_all_remaining_steps() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)

    def fail(_value: object, state: _ResearchContext) -> None:
        state.calls.append("broken")
        raise RuntimeError("source unavailable")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source", lambda value: value, fail, failure_mode="stop"
            ),
            ConfigActivationStep(
                "index",
                lambda value: value,
                lambda _value, state: state.calls.append("index"),
            ),
            ConfigActivationStep(
                "renderer",
                lambda value: value,
                lambda _value, state: state.calls.append("renderer"),
            ),
        )
    )

    report = runtime.start(_ResearchConfig(), context)

    assert calls == ["broken"]
    assert _statuses(report) == {
        "source": "failed",
        "index": "blocked",
        "renderer": "blocked",
    }
    assert report.ok is False


def test_start_can_roll_back_already_applied_steps_after_failure() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)

    def fail(_value: object, _context: _ResearchContext) -> None:
        raise RuntimeError("renderer unavailable")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, state: state.calls.append("start:source"),
                dispose=lambda state: state.calls.append("dispose:source"),
            ),
            ConfigActivationStep(
                "renderer",
                lambda value: value,
                fail,
                depends_on=("source",),
            ),
        ),
        rollback_on_start_failure=True,
    )

    report = runtime.start(_ResearchConfig(), context)

    assert report.ok is False
    assert calls == ["start:source", "dispose:source"]


def test_sync_entry_point_rejects_async_step() -> None:
    async def apply(_value: object, _context: _ResearchContext) -> None:
        await asyncio.sleep(0)

    runtime = ConfigActivationRuntime(
        (ConfigActivationStep("source", lambda value: value, apply),)
    )

    report = runtime.start(_ResearchConfig(), _ResearchContext([]))

    assert _statuses(report) == {"source": "failed"}
    assert isinstance(report.failures[0].error, TypeError)
    with pytest.raises(RuntimeError, match="awaitable"):
        report.raise_for_failure()


def test_dispose_runs_in_reverse_order_and_is_idempotent() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
                dispose=lambda state: state.calls.append("source"),
            ),
            ConfigActivationStep(
                "index",
                lambda value: value,
                lambda _value, _context: None,
                depends_on=("source",),
                dispose=lambda state: state.calls.append("index"),
            ),
            ConfigActivationStep(
                "renderer",
                lambda value: value,
                lambda _value, _context: None,
                depends_on=("index",),
                dispose=lambda state: state.calls.append("renderer"),
            ),
        )
    )
    runtime.start(_ResearchConfig(), context)

    first = runtime.dispose(context)
    second = runtime.dispose(context)

    assert calls == ["renderer", "index", "source"]
    assert first.operation == second.operation == "dispose"
    assert _statuses(first) == {
        "renderer": "applied",
        "index": "applied",
        "source": "applied",
    }
    assert second.results == ()


def test_dispose_retains_failed_step_for_retry() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)
    attempts = 0

    def dispose(state: _ResearchContext) -> None:
        nonlocal attempts
        attempts += 1
        state.calls.append(f"dispose:{attempts}")
        if attempts == 1:
            raise RuntimeError("resource still busy")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
                dispose=dispose,
            ),
        )
    )
    runtime.start(_ResearchConfig(), context)

    first = runtime.dispose(context)
    with pytest.raises(RuntimeError, match="cleanup is incomplete"):
        runtime.refresh(_ResearchConfig(), context)
    second = runtime.dispose(context)
    third = runtime.dispose(context)

    assert _statuses(first) == {"source": "failed"}
    assert first.ok is False
    assert _statuses(second) == {"source": "applied"}
    assert second.ok is True
    assert third.results == ()
    assert calls == ["dispose:1", "dispose:2"]


def test_dispose_failure_blocks_dependency_cleanup_until_retry() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)
    child_attempts = 0

    def dispose_child(state: _ResearchContext) -> None:
        nonlocal child_attempts
        child_attempts += 1
        state.calls.append(f"child:{child_attempts}")
        if child_attempts == 1:
            raise RuntimeError("child still active")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "parent",
                lambda value: value,
                lambda _value, _context: None,
                dispose=lambda state: state.calls.append("parent"),
            ),
            ConfigActivationStep(
                "child",
                lambda value: value,
                lambda _value, _context: None,
                depends_on=("parent",),
                dispose=dispose_child,
            ),
        )
    )
    runtime.start(_ResearchConfig(), context)

    first = runtime.dispose(context)
    second = runtime.dispose(context)

    assert _statuses(first) == {"child": "failed", "parent": "blocked"}
    assert calls == ["child:1", "child:2", "parent"]
    assert _statuses(second) == {"child": "applied", "parent": "applied"}


def test_failed_start_rollback_remains_disposable() -> None:
    calls: list[str] = []
    context = _ResearchContext(calls)
    dispose_attempts = 0

    def dispose(state: _ResearchContext) -> None:
        nonlocal dispose_attempts
        dispose_attempts += 1
        state.calls.append(f"dispose:{dispose_attempts}")
        if dispose_attempts == 1:
            raise RuntimeError("rollback failed")

    def fail(_value: object, _context: _ResearchContext) -> None:
        raise RuntimeError("activation failed")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, state: state.calls.append("start:source"),
                dispose=dispose,
            ),
            ConfigActivationStep(
                "renderer",
                lambda value: value,
                fail,
                depends_on=("source",),
            ),
        ),
        rollback_on_start_failure=True,
    )

    started = runtime.start(_ResearchConfig(), context)
    disposed = runtime.dispose(context)

    assert [(failure.step, failure.operation) for failure in started.failures] == [
        ("renderer", "start"),
        ("source", "dispose"),
    ]
    assert _statuses(disposed) == {"source": "applied"}
    assert calls == ["start:source", "dispose:1", "dispose:2"]


def test_runtime_rejects_sync_reentrancy() -> None:
    context = _ResearchContext([])
    runtime: ConfigActivationRuntime[_ResearchConfig, _ResearchContext]

    def reenter(_value: object, state: _ResearchContext) -> None:
        runtime.refresh(_ResearchConfig(), state)

    runtime = ConfigActivationRuntime(
        (ConfigActivationStep("source", lambda value: value, reenter),)
    )

    report = runtime.start(_ResearchConfig(), context)

    assert _statuses(report) == {"source": "failed"}
    assert isinstance(report.failures[0].error, RuntimeError)
    assert "reentrant" in str(report.failures[0].error)


def test_runtime_instance_cannot_mix_sync_and_async_operations() -> None:
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
            ),
        )
    )
    context = _ResearchContext([])
    runtime.start(_ResearchConfig(), context)

    async def activate() -> None:
        await runtime.astart(_ResearchConfig(), context)

    with pytest.raises(RuntimeError, match="cannot mix sync and async"):
        asyncio.run(activate())


def test_runtime_binds_one_lifecycle_to_its_start_context() -> None:
    first_context = _ResearchContext([])
    second_context = _ResearchContext([])
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
            ),
        )
    )

    runtime.start(_ResearchConfig(), first_context)

    with pytest.raises(RuntimeError, match="already started"):
        runtime.start(_ResearchConfig(), first_context)
    with pytest.raises(RuntimeError, match="context passed to start"):
        runtime.refresh(_ResearchConfig(), second_context)
    with pytest.raises(RuntimeError, match="context passed to start"):
        runtime.dispose(second_context)

    runtime.dispose(first_context)
    restarted = runtime.start(_ResearchConfig(), second_context)

    assert restarted.ok is True


def test_refresh_requires_start() -> None:
    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
            ),
        )
    )

    with pytest.raises(RuntimeError, match="started before refresh"):
        runtime.refresh(_ResearchConfig(), _ResearchContext([]))


def test_async_lifecycle_awaits_steps_serially() -> None:
    calls: list[str] = []
    active = 0
    max_active = 0

    async def apply(name: str, value: str, state: _ResearchContext) -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        state.calls.append(f"start:{name}:{value}")
        await asyncio.sleep(0)
        state.calls.append(f"end:{name}:{value}")
        active -= 1

    async def dispose(name: str, state: _ResearchContext) -> None:
        state.calls.append(f"dispose:{name}")
        await asyncio.sleep(0)

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value.source_revision,
                lambda value, state: apply("source", value, state),
                dispose=lambda state: dispose("source", state),
            ),
            ConfigActivationStep(
                "index",
                lambda value: value.index_profile,
                lambda value, state: apply("index", value, state),
                depends_on=("source",),
                dispose=lambda state: dispose("index", state),
            ),
        )
    )
    context = _ResearchContext(calls)

    async def scenario() -> tuple[object, object, object]:
        started = await runtime.astart(_ResearchConfig(), context)
        refreshed = await runtime.arefresh(
            _ResearchConfig(source_revision="v2", index_profile="deep"),
            context,
        )
        disposed = await runtime.adispose(context)
        return started, refreshed, disposed

    started, refreshed, disposed = asyncio.run(scenario())

    assert started.ok and refreshed.ok and disposed.ok
    assert started.operation == "start"
    assert refreshed.operation == "refresh"
    assert disposed.operation == "dispose"
    assert max_active == 1
    assert calls == [
        "start:source:v1",
        "end:source:v1",
        "start:index:balanced",
        "end:index:balanced",
        "start:source:v2",
        "end:source:v2",
        "start:index:deep",
        "end:index:deep",
        "dispose:index",
        "dispose:source",
    ]


def test_async_cascade_cancellation_is_retried() -> None:
    child_attempts = 0

    async def apply_child(_value: object, _context: _ResearchContext) -> None:
        nonlocal child_attempts
        child_attempts += 1
        await asyncio.sleep(0)
        if child_attempts == 2:
            raise asyncio.CancelledError

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value.source_revision,
                lambda _value, _context: None,
            ),
            ConfigActivationStep(
                "index",
                lambda value: value.index_profile,
                apply_child,
                depends_on=("source",),
            ),
        )
    )
    context = _ResearchContext([])

    async def scenario() -> object:
        await runtime.astart(_ResearchConfig(), context)
        with pytest.raises(asyncio.CancelledError):
            await runtime.arefresh(
                _ResearchConfig(source_revision="v2"),
                context,
            )
        return await runtime.arefresh(
            _ResearchConfig(source_revision="v2"),
            context,
        )

    retried = asyncio.run(scenario())

    assert _statuses(retried) == {"source": "skipped", "index": "applied"}
    assert child_attempts == 3


def test_async_dispose_retains_failed_step_for_retry() -> None:
    attempts = 0

    async def dispose(_context: _ResearchContext) -> None:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0)
        if attempts == 1:
            raise RuntimeError("resource still busy")

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
                dispose=dispose,
            ),
        )
    )
    context = _ResearchContext([])

    async def scenario() -> tuple[object, object, object]:
        await runtime.astart(_ResearchConfig(), context)
        first = await runtime.adispose(context)
        with pytest.raises(RuntimeError, match="cleanup is incomplete"):
            await runtime.arefresh(_ResearchConfig(), context)
        second = await runtime.adispose(context)
        third = await runtime.adispose(context)
        return first, second, third

    first, second, third = asyncio.run(scenario())

    assert _statuses(first) == {"source": "failed"}
    assert _statuses(second) == {"source": "applied"}
    assert third.results == ()  # type: ignore[attr-defined]


def test_async_dispose_cancellation_requires_cleanup_retry() -> None:
    attempts = 0

    async def dispose(_context: _ResearchContext) -> None:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0)
        if attempts == 1:
            raise asyncio.CancelledError

    runtime = ConfigActivationRuntime(
        (
            ConfigActivationStep(
                "source",
                lambda value: value,
                lambda _value, _context: None,
                dispose=dispose,
            ),
        )
    )
    context = _ResearchContext([])

    async def scenario() -> object:
        await runtime.astart(_ResearchConfig(), context)
        with pytest.raises(asyncio.CancelledError):
            await runtime.adispose(context)
        with pytest.raises(RuntimeError, match="cleanup is incomplete"):
            await runtime.arefresh(_ResearchConfig(), context)
        return await runtime.adispose(context)

    disposed = asyncio.run(scenario())

    assert _statuses(disposed) == {"source": "applied"}
    assert attempts == 2


def test_runtime_rejects_async_reentrancy() -> None:
    context = _ResearchContext([])
    runtime: ConfigActivationRuntime[_ResearchConfig, _ResearchContext]

    async def reenter(_value: object, state: _ResearchContext) -> None:
        await runtime.arefresh(_ResearchConfig(), state)

    runtime = ConfigActivationRuntime(
        (ConfigActivationStep("source", lambda value: value, reenter),)
    )

    async def activate() -> object:
        return await runtime.astart(_ResearchConfig(), context)

    report = asyncio.run(activate())

    assert _statuses(report) == {"source": "failed"}
    assert isinstance(report.failures[0].error, RuntimeError)  # type: ignore[attr-defined]
    assert "reentrant" in str(report.failures[0].error)  # type: ignore[attr-defined]
