from __future__ import annotations

import asyncio

import pytest

from loushang.harness.runtime import (
    RegistrationDisposalResult,
    RegistrationIdentity,
    RegistrationLease,
    RegistrationOwner,
    RegistrationScope,
)


def _owner(owner_id: str = "extension:alpha") -> RegistrationOwner:
    return RegistrationOwner(
        owner_kind="extension",
        owner_id=owner_id,
        runtime_id="runtime:test",
        generation=1,
    )


def test_registration_lease_removes_only_its_exact_same_name_entry() -> None:
    owner = _owner()
    first_identity = RegistrationIdentity.create(
        surface="tool",
        public_key="search",
    )
    second_identity = RegistrationIdentity.create(
        surface="tool",
        public_key="search",
    )
    entries = {
        first_identity.registration_id: "first",
        second_identity.registration_id: "second",
    }
    calls: list[str] = []

    def lease_for(identity: RegistrationIdentity) -> RegistrationLease:
        def remove() -> RegistrationDisposalResult:
            calls.append(identity.registration_id)
            if entries.pop(identity.registration_id, None) is None:
                return RegistrationDisposalResult(state="already_removed")
            return RegistrationDisposalResult(state="removed")

        return RegistrationLease(owner=owner, identity=identity, dispose=remove)

    first = lease_for(first_identity)
    second = lease_for(second_identity)

    async def scenario() -> None:
        assert await first.dispose() == RegistrationDisposalResult(state="removed")
        assert entries == {second_identity.registration_id: "second"}
        assert await first.dispose() == RegistrationDisposalResult(
            state="already_removed"
        )
        assert await second.dispose() == RegistrationDisposalResult(state="removed")

    asyncio.run(scenario())

    assert first_identity.registration_id != second_identity.registration_id
    assert calls == [
        first_identity.registration_id,
        second_identity.registration_id,
    ]


def test_registration_scope_rejects_a_lease_owned_by_another_owner() -> None:
    scope = RegistrationScope(_owner("extension:alpha"))
    foreign = RegistrationLease(
        owner=_owner("extension:beta"),
        identity=RegistrationIdentity.create(surface="tool", public_key="search"),
        dispose=lambda: None,
    )

    with pytest.raises(ValueError, match="owner"):
        scope.add(foreign)

    assert foreign.state == "active"


def test_registration_scope_disposes_in_reverse_and_continues_after_failure() -> None:
    owner = _owner()
    calls: list[str] = []
    scope = RegistrationScope(owner)

    def add(name: str, *, fail: bool = False) -> None:
        def remove() -> None:
            calls.append(name)
            if fail:
                raise RuntimeError(f"cannot remove {name}")

        scope.add(
            RegistrationLease(
                owner=owner,
                identity=RegistrationIdentity.create(
                    surface="test",
                    public_key=name,
                ),
                dispose=remove,
            )
        )

    add("first")
    add("second", fail=True)
    add("third")
    scope.commit()

    report = asyncio.run(scope.dispose())

    assert calls == ["third", "second", "first"]
    assert [outcome.identity.public_key for outcome in report.outcomes] == [
        "third",
        "second",
        "first",
    ]
    assert [outcome.result.state for outcome in report.outcomes] == [
        "removed",
        "failed_retryable",
        "removed",
    ]
    assert report.has_failures is True
    assert scope.state == "failed_retryable"


def test_registration_scope_dispose_is_idempotent_after_success() -> None:
    owner = _owner()
    calls = 0
    scope = RegistrationScope(owner)

    def remove() -> None:
        nonlocal calls
        calls += 1

    lease = scope.add(
        RegistrationLease(
            owner=owner,
            identity=RegistrationIdentity.create(
                surface="test",
                public_key="entry",
            ),
            dispose=remove,
        )
    )
    scope.commit()

    async def scenario() -> None:
        first = await scope.dispose()
        second = await scope.dispose()
        assert second is first
        assert await lease.dispose() == RegistrationDisposalResult(
            state="already_removed"
        )

    asyncio.run(scenario())

    assert calls == 1
    assert scope.state == "disposed"


def test_registration_lease_retries_only_a_retryable_failure() -> None:
    attempts = 0

    def remove() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary removal failure")

    lease = RegistrationLease(
        owner=_owner(),
        identity=RegistrationIdentity.create(
            surface="test",
            public_key="entry",
        ),
        dispose=remove,
    )

    async def scenario() -> None:
        first = await lease.dispose()
        assert first.state == "failed_retryable"
        assert first.diagnostic_code == "registration_disposer_failed"
        assert lease.state == "failed_retryable"

        assert await lease.dispose() == RegistrationDisposalResult(state="removed")
        assert await lease.dispose() == RegistrationDisposalResult(
            state="already_removed"
        )

    asyncio.run(scenario())

    assert attempts == 2


def test_registration_scope_finishes_cleanup_before_propagating_cancellation() -> None:
    owner = _owner()
    calls: list[str] = []

    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        scope = RegistrationScope(owner)

        async def remove_second() -> None:
            calls.append("second:start")
            started.set()
            await release.wait()
            calls.append("second:end")

        scope.add(
            RegistrationLease(
                owner=owner,
                identity=RegistrationIdentity.create(
                    surface="test",
                    public_key="first",
                ),
                dispose=lambda: calls.append("first"),
            )
        )
        scope.add(
            RegistrationLease(
                owner=owner,
                identity=RegistrationIdentity.create(
                    surface="test",
                    public_key="second",
                ),
                dispose=remove_second,
            )
        )
        scope.commit()

        disposing = asyncio.create_task(scope.dispose())
        await started.wait()
        disposing.cancel()
        release.set()

        with pytest.raises(asyncio.CancelledError):
            await disposing

        assert scope.state == "disposed"

    asyncio.run(scenario())

    assert calls == ["second:start", "second:end", "first"]


def test_uncommitted_registration_scope_rolls_back_on_context_exit() -> None:
    owner = _owner()
    calls: list[str] = []

    async def scenario() -> None:
        async with RegistrationScope(owner) as scope:
            scope.add(
                RegistrationLease(
                    owner=owner,
                    identity=RegistrationIdentity.create(
                        surface="test",
                        public_key="entry",
                    ),
                    dispose=lambda: calls.append("removed"),
                )
            )

        assert scope.state == "disposed"

    asyncio.run(scenario())

    assert calls == ["removed"]
