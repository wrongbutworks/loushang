from __future__ import annotations

from typing import Any

from loushang.coding.compaction.types import CompactionResult, CompactionStatus
from loushang.harness.context.compaction import (
    CompactionCoordinator as HarnessCompactionCoordinator,
)


class CompactionCoordinator:
    """Thin service boundary for session compaction orchestration."""

    def __init__(self) -> None:
        self._coordinator: HarnessCompactionCoordinator[CompactionResult | None] = (
            HarnessCompactionCoordinator()
        )

    def get_status(self) -> CompactionStatus:
        status = self._coordinator.get_status()
        return CompactionStatus(
            is_compacting=status.is_compacting,
            last_reason=status.last_reason,
            last_result=(
                status.last_result
                if isinstance(status.last_result, CompactionResult)
                else None
            ),
            last_error=status.last_error,
            aborted=status.aborted,
        )

    async def compact_session(
        self,
        session: Any,
        *,
        custom_instructions: str | None = None,
    ) -> CompactionResult:
        async def operation() -> CompactionResult:
            compact_session = getattr(session, "compact_session", None)
            if callable(compact_session):
                return await compact_session(custom_instructions=custom_instructions)
            return await session.compact(custom_instructions=custom_instructions)

        result = await self._coordinator.run(
            operation,
            reason="manual",
            abort_driver=_abort_driver(session),
        )
        if result is None:
            raise RuntimeError("Manual compaction did not produce a result")
        return result

    async def maybe_compact_after_turn(self, session: Any, assistant_message: object) -> CompactionResult | None:
        if self._coordinator.is_compacting:
            return None

        async def operation() -> CompactionResult | None:
            maybe_compact = getattr(session, "maybe_compact_after_turn", None)
            if callable(maybe_compact):
                return await maybe_compact(assistant_message)
            checker = getattr(session, "_check_auto_compaction", None)
            return await checker(assistant_message) if callable(checker) else None

        return await self._coordinator.run(
            operation,
            reason="threshold",
            abort_driver=_abort_driver(session),
        )

    def abort(self) -> None:
        self._coordinator.abort()


def _abort_driver(session: Any):
    abort_compaction = getattr(session, "abort_compaction", None)
    return abort_compaction if callable(abort_compaction) else None
