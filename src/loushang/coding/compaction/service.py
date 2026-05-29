from __future__ import annotations

from typing import Any

from loushang.coding.compaction.types import CompactionResult, CompactionStatus


class CompactionCoordinator:
    """Thin service boundary for session compaction orchestration."""

    def __init__(self) -> None:
        self._active_session: Any | None = None
        self._is_compacting = False
        self._last_reason: str | None = None
        self._last_result: CompactionResult | None = None
        self._last_error: str | None = None
        self._aborted = False

    def get_status(self) -> CompactionStatus:
        return CompactionStatus(
            is_compacting=self._is_compacting,
            last_reason=self._last_reason,
            last_result=self._last_result,
            last_error=self._last_error,
            aborted=self._aborted,
        )

    async def compact_session(
        self,
        session: Any,
        *,
        custom_instructions: str | None = None,
    ) -> CompactionResult:
        if self._is_compacting:
            raise RuntimeError("Compaction already in progress")
        self._begin(session, reason="manual")
        try:
            compact_session = getattr(session, "compact_session", None)
            if callable(compact_session):
                result = await compact_session(custom_instructions=custom_instructions)
            else:
                result = await session.compact(custom_instructions=custom_instructions)
            self._last_result = result
            return result
        except Exception as exc:
            self._last_error = str(exc)
            raise
        finally:
            self._finish()

    async def maybe_compact_after_turn(self, session: Any, assistant_message: object) -> CompactionResult | None:
        if self._is_compacting:
            return None
        self._begin(session, reason="threshold")
        try:
            maybe_compact = getattr(session, "maybe_compact_after_turn", None)
            if callable(maybe_compact):
                result = await maybe_compact(assistant_message)
            else:
                checker = getattr(session, "_check_auto_compaction", None)
                result = await checker(assistant_message) if callable(checker) else None
            if isinstance(result, CompactionResult):
                self._last_result = result
            return result
        except Exception as exc:
            self._last_error = str(exc)
            raise
        finally:
            self._finish()

    def abort(self) -> None:
        self._aborted = True
        session = self._active_session
        if session is None:
            return
        abort_compaction = getattr(session, "abort_compaction", None)
        if callable(abort_compaction):
            abort_compaction()

    def _begin(self, session: Any, *, reason: str) -> None:
        self._active_session = session
        self._is_compacting = True
        self._last_reason = reason
        self._last_error = None
        self._aborted = False

    def _finish(self) -> None:
        self._is_compacting = False
        self._active_session = None
