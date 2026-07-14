from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from loushang.harness.runtime.navigation import NavigationTransactionCoordinator


@dataclass
class _AbortScope:
    aborted: bool = False

    def abort(self) -> None:
        self.aborted = True


def test_navigation_transaction_orders_lifecycle_and_clears_scope() -> None:
    events: list[str] = []
    coordinator = NavigationTransactionCoordinator(
        create_abort_scope=_AbortScope,
        abort=lambda scope: scope.abort(),
    )

    async def commit(plan: str, scope: _AbortScope) -> str:
        assert coordinator.is_active is True
        assert scope.aborted is False
        events.append(f"commit:{plan}")
        return "done"

    result = asyncio.run(
        coordinator.run(
            "branch-2",
            before_commit=lambda plan: events.append(f"start:{plan}"),
            commit=commit,
            after_commit=lambda plan, value: events.append(f"end:{plan}:{value}"),
        )
    )

    assert result == "done"
    assert coordinator.is_active is False
    assert events == ["start:branch-2", "commit:branch-2", "end:branch-2:done"]


def test_navigation_transaction_exposes_abort_and_reports_failure() -> None:
    events: list[str] = []
    coordinator = NavigationTransactionCoordinator(
        create_abort_scope=_AbortScope,
        abort=lambda scope: scope.abort(),
    )

    async def commit(_plan: str, scope: _AbortScope) -> str:
        assert coordinator.abort() is True
        assert scope.aborted is True
        raise RuntimeError("summary failed")

    with pytest.raises(RuntimeError, match="summary failed"):
        asyncio.run(
            coordinator.run(
                "branch-2",
                commit=commit,
                on_failure=lambda failure: events.append(
                    f"failure:{failure.plan}:{failure.error}"
                ),
            )
        )

    assert coordinator.is_active is False
    assert coordinator.abort() is False
    assert events == ["failure:branch-2:summary failed"]
