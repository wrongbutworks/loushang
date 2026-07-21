from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from loushang.harness.session import (
    AgentTranscriptSessionRuntime,
    ProductTranscriptSessionLifecyclePorts,
    ProductTranscriptSessionLifecycleStore,
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


@dataclass
class _TranscriptSession:
    ref: str
    cwd: str
    leaf_id: str = "leaf"


class _ProductPorts:
    def __init__(self) -> None:
        self.actions: list[tuple[object, ...]] = []
        self.disposed: list[str] = []

    async def create(
        self,
        cwd: str,
        parent_session_ref: str | None,
    ) -> _TranscriptSession:
        self.actions.append(("create", cwd, parent_session_ref))
        return _TranscriptSession("new.jsonl", cwd)

    async def restore(
        self,
        session_ref: str | Path,
        cwd_override: str | None,
    ) -> _TranscriptSession:
        self.actions.append(("restore", str(session_ref), cwd_override))
        return _TranscriptSession(str(session_ref), cwd_override or "/restored")

    async def fork(
        self,
        transcript: _TranscriptSession,
        target_entry_id: str | None,
    ) -> _TranscriptSession:
        self.actions.append(("fork", transcript.ref, target_entry_id))
        return _TranscriptSession("fork.jsonl", transcript.cwd)

    async def dispose(self, transcript: _TranscriptSession) -> None:
        self.disposed.append(transcript.ref)

    @staticmethod
    def transcript_for_session(session: _Session) -> _TranscriptSession:
        return _TranscriptSession(session.ref, session.cwd, session.leaf_id)

    @staticmethod
    def cwd(transcript: _TranscriptSession) -> str:
        return transcript.cwd

    @staticmethod
    def session_ref(transcript: _TranscriptSession) -> str:
        return transcript.ref

    @staticmethod
    def leaf_entry_id(transcript: _TranscriptSession) -> str:
        return transcript.leaf_id

    def lifecycle_ports(
        self,
    ) -> ProductTranscriptSessionLifecyclePorts[_TranscriptSession, _Session]:
        return ProductTranscriptSessionLifecyclePorts(
            create_transcript=self.create,
            restore_transcript=self.restore,
            fork_transcript=self.fork,
            dispose_transcript=self.dispose,
            transcript_for_session=self.transcript_for_session,
            transcript_cwd=self.cwd,
            transcript_session_ref=self.session_ref,
            transcript_leaf_entry_id=self.leaf_entry_id,
        )


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


def test_product_transcript_store_creates_and_forks_runtime_sessions() -> None:
    async def scenario() -> None:
        ports = _ProductPorts()
        store = ProductTranscriptSessionLifecycleStore(
            ports=ports.lifecycle_ports(),
            build_session=lambda transcript, _current, _transition: _Session(
                transcript.ref,
                transcript.cwd,
                transcript.leaf_id,
            ),
        )
        lifecycle = SessionLifecycleRuntime[_Session, object](
            store=store,
            hooks=SessionLifecycleHooks(dispose_session=lambda _session: None),
        )

        created = await lifecycle.new(cwd="/project", parent_session_ref="parent")
        forked = await lifecycle.fork("leaf")

        assert created.current == _Session("new.jsonl", "/project")
        assert forked.current == _Session("fork.jsonl", "/project")
        assert ports.actions == [
            ("create", "/project", "parent"),
            ("fork", "new.jsonl", "leaf"),
        ]

    asyncio.run(scenario())


def test_product_transcript_store_disposes_restore_when_runtime_build_fails() -> None:
    async def scenario() -> None:
        ports = _ProductPorts()
        store = ProductTranscriptSessionLifecycleStore(
            ports=ports.lifecycle_ports(),
            build_session=lambda _transcript, _current, _transition: _raise_build(),
        )
        lifecycle = SessionLifecycleRuntime[_Session, object](
            store=store,
            hooks=SessionLifecycleHooks(dispose_session=lambda _session: None),
        )

        with pytest.raises(RuntimeError, match="build failed"):
            await lifecycle.restore("saved.jsonl")

        assert ports.disposed == ["saved.jsonl"]

    asyncio.run(scenario())


def _raise_build() -> _Session:
    raise RuntimeError("build failed")
