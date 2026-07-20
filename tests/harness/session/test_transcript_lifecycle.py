from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from loushang.harness.session import (
    AgentTranscriptSessionRuntime,
    SessionLifecycleHooks,
    SessionLifecycleRuntime,
    SessionLifecycleTransition,
)


@dataclass(frozen=True)
class _Session:
    ref: str
    cwd: str
    leaf_id: str = "leaf"


class _Store:
    def __init__(self) -> None:
        self.actions: list[tuple[object, ...]] = []

    async def create(
        self,
        current: _Session | None,
        transition: SessionLifecycleTransition,
        *,
        cwd: str,
        parent_session_ref: str | None,
    ) -> _Session:
        self.actions.append(
            ("create", current, transition.reason, cwd, parent_session_ref)
        )
        return _Session("new", cwd)

    async def restore(
        self,
        current: _Session | None,
        transition: SessionLifecycleTransition,
        session_ref: str | Path,
        *,
        cwd_override: str | None = None,
    ) -> _Session:
        cwd = cwd_override or "/restored"
        self.actions.append(("restore", current, transition.reason, str(session_ref)))
        return _Session(str(session_ref), cwd)

    async def fork(
        self,
        session: _Session,
        transition: SessionLifecycleTransition,
        target_entry_id: str | None,
    ) -> _Session:
        self.actions.append(
            ("fork", session.ref, transition.fork_position, target_entry_id)
        )
        return _Session("fork", session.cwd)

    def get_cwd(self, session: _Session) -> str:
        return session.cwd

    def get_session_ref(self, session: _Session) -> str:
        return session.ref

    def get_leaf_entry_id(self, session: _Session) -> str:
        return session.leaf_id


def test_transcript_session_runtime_delegates_lifecycle_operations(tmp_path) -> None:
    async def scenario() -> None:
        store = _Store()
        disposed: list[str] = []
        lifecycle = SessionLifecycleRuntime[_Session, object](
            store=store,
            hooks=SessionLifecycleHooks(
                dispose_session=lambda session: disposed.append(session.ref)
            ),
        )
        runtime = AgentTranscriptSessionRuntime(
            session_dir=tmp_path,
            lifecycle=lifecycle,
        )

        created = await runtime.new_session_operation(
            cwd="/project",
            parent_session_ref="parent.jsonl",
            metadata={"operation": "new"},
        )
        assert created.current == _Session("new", "/project")
        assert runtime.session is created.current
        assert runtime.cwd == "/project"

        forked = await runtime.fork_session_operation("leaf", position="at")
        assert forked.current == _Session("fork", "/project")
        assert runtime.get_current_session() is forked.current

        await runtime.dispose_session_runtime(metadata={"operation": "dispose"})
        assert disposed == ["new", "fork"]
        assert store.actions == [
            ("create", None, "new", "/project", "parent.jsonl"),
            ("fork", "new", "at", "leaf"),
        ]

    asyncio.run(scenario())


def test_transcript_session_runtime_resolves_current_native_session_id(
    tmp_path,
) -> None:
    session_file = tmp_path / "2026-07-20_demo-session.jsonl"
    session_file.write_text("{}\n", encoding="utf-8")
    lifecycle = SessionLifecycleRuntime[_Session, object](
        store=_Store(),
        hooks=SessionLifecycleHooks(dispose_session=lambda _session: None),
    )
    runtime = AgentTranscriptSessionRuntime(session_dir=tmp_path, lifecycle=lifecycle)

    assert runtime.resolve_session_file("demo-session") == session_file
