from __future__ import annotations

import asyncio
from types import SimpleNamespace

from loushang.harness.session import (
    SessionLifecycleTransition,
    build_agent_session_lifecycle_hooks,
    prepare_current_agent_session,
)


class _Manager:
    def __init__(self, cwd: str, session_file: str) -> None:
        self._cwd = cwd
        self.session_file = session_file

    def get_cwd(self) -> str:
        return self._cwd


class _Runner:
    def __init__(self, actions: list[tuple[object, ...]]) -> None:
        self.actions = actions

    async def before_session_fork(self, event: object) -> object:
        self.actions.append(("before-fork", event.entry_id, event.position))
        return SimpleNamespace(cancel=False)

    async def before_session_switch(self, event: object) -> object:
        self.actions.append(("before-switch", event.reason))
        return SimpleNamespace(cancel=False)

    async def emit_session_shutdown(self, event: object) -> None:
        self.actions.append(("shutdown", event.reason, event.target_session_file))


class _Session:
    def __init__(self, actions: list[tuple[object, ...]], name: str) -> None:
        self.actions = actions
        self.session_manager = _Manager(f"/{name}", f"/{name}.jsonl")
        self.extension_runner = _Runner(actions)
        self.diagnostics_service = None
        self.disposed = False

    def _stage_session_approvals(self) -> None:
        self.actions.append(("stage-approvals",))

    def _open_session_approvals(self) -> None:
        self.actions.append(("open-approvals",))

    def set_extension_runtime_host(self, host: object) -> None:
        self.actions.append(("bind-host", host))

    async def start_extension_runtime(self, *, reason: str) -> None:
        self.actions.append(("start-extensions", reason))

    def _sync_extension_diagnostics(self, *, phase: str) -> None:
        self.actions.append(("sync-diagnostics", phase))

    async def dispose(self) -> None:
        self.disposed = True


def test_agent_session_lifecycle_hooks_bind_existing_session_capabilities() -> None:
    async def scenario() -> None:
        actions: list[tuple[object, ...]] = []
        runtime_host = object()
        session = _Session(actions, "current")
        target = _Session(actions, "target")
        failures: list[Exception] = []
        hooks = build_agent_session_lifecycle_hooks(
            runtime_host=runtime_host,
            record_shutdown_failure=lambda _session, _event, exc: failures.append(exc),
        )
        transition = SessionLifecycleTransition(
            reason="fork",
            fork_entry_id="entry-1",
            fork_position="before",
        )

        assert hooks.before_transition is not None
        decision = await hooks.before_transition(session, transition)
        assert decision is not None and decision.cancelled is False
        assert hooks.prepare_session is not None
        hooks.prepare_session(session, None, transition)
        assert hooks.activate_session is not None
        await hooks.activate_session(session, None, transition)
        assert hooks.before_release is not None
        await hooks.before_release(session, target, transition)
        assert hooks.dispose_session is not None
        await hooks.dispose_session(session)

        assert failures == []
        assert session.disposed is True
        assert actions == [
            ("before-fork", "entry-1", "before"),
            ("sync-diagnostics", "runtime"),
            ("stage-approvals",),
            ("bind-host", runtime_host),
            ("open-approvals",),
            ("start-extensions", "fork"),
            ("shutdown", "fork", "/target.jsonl"),
            ("sync-diagnostics", "runtime"),
        ]

    asyncio.run(scenario())


def test_prepare_current_agent_session_reopens_and_binds_runtime_host() -> None:
    actions: list[tuple[object, ...]] = []
    session = _Session(actions, "current")
    runtime_host = object()

    prepare_current_agent_session(session, runtime_host)

    assert actions == [("open-approvals",), ("bind-host", runtime_host)]
