from __future__ import annotations

import asyncio

import pytest

from loushang.harness.runtime import SessionTransitionHost


def test_transition_host_orders_release_activation_and_rebind() -> None:
    events: list[tuple[str, str | None]] = []

    async def dispose(session: str) -> None:
        events.append(("dispose", session))

    async def rebind(session: str) -> None:
        events.append(("rebind", session))

    host = SessionTransitionHost(
        "first",
        dispose=dispose,
        rebind=rebind,
        before_invalidate=lambda: events.append(("invalidate", None)),
    )

    async def scenario() -> None:
        await host.replace(
            "second",
            prepare=lambda session: events.append(("prepare", session)),
            before_release=lambda session: events.append(("release", session)),
            activate=lambda session: events.append(("activate", session)),
        )

    asyncio.run(scenario())

    assert events == [
        ("prepare", "second"),
        ("release", "first"),
        ("invalidate", None),
        ("dispose", "first"),
        ("activate", "second"),
        ("rebind", "second"),
    ]
    assert host.current == "second"


def test_transition_host_preserves_current_when_prepare_fails() -> None:
    async def dispose(session: str) -> None:
        del session

    host = SessionTransitionHost("first", dispose=dispose)

    async def fail_prepare(session: str) -> None:
        del session
        raise RuntimeError("prepare failed")

    with pytest.raises(RuntimeError, match="prepare failed"):
        asyncio.run(host.replace("second", prepare=fail_prepare))

    assert host.current == "first"


def test_transition_host_serializes_concurrent_replacements() -> None:
    dispose_started = asyncio.Event()
    dispose_release = asyncio.Event()
    disposed: list[str] = []

    async def dispose(session: str) -> None:
        disposed.append(session)
        if session == "first":
            dispose_started.set()
            await dispose_release.wait()

    host = SessionTransitionHost("first", dispose=dispose)

    async def scenario() -> list[str]:
        second_task = asyncio.create_task(host.replace("second"))
        await dispose_started.wait()
        third_task = asyncio.create_task(host.replace("third"))
        await asyncio.sleep(0)
        assert host.current == "first"
        dispose_release.set()
        return await asyncio.gather(second_task, third_task)

    assert asyncio.run(scenario()) == ["second", "third"]
    assert disposed == ["first", "second"]
    assert host.current == "third"


def test_transition_host_allows_reentrant_transition_callbacks() -> None:
    rebound: list[str] = []

    async def dispose(session: str) -> None:
        del session

    host = SessionTransitionHost("first", dispose=dispose)

    async def rebind(session: str) -> None:
        rebound.append(session)
        async with host.transition():
            assert host.current == session

    host.set_rebind(rebind)

    asyncio.run(host.replace("second"))

    assert rebound == ["second"]


def test_transition_host_disposes_current_idempotently() -> None:
    disposed: list[str] = []
    host = SessionTransitionHost(
        "first", dispose=lambda session: disposed.append(session)
    )

    async def scenario() -> None:
        await host.dispose_current()
        await host.dispose_current()

    asyncio.run(scenario())

    assert disposed == ["first"]
    assert host.current is None
