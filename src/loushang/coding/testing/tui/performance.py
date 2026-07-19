from __future__ import annotations

from pathlib import Path
from typing import Any

from loushang.coding.presentation.tui.history import session_history_records
from loushang.coding.store.session_manager import SessionManager
from loushang.tui.transcript import DisplayRecord


async def load_session_history_records(
    session_file: str | Path,
    *,
    tool_definition_resolver: Any | None = None,
) -> tuple[DisplayRecord, ...]:
    """Load persisted Coding history for a generic transcript probe."""

    manager = await SessionManager.load(Path(session_file).expanduser().resolve())
    session = _HistorySession(manager)
    return session_history_records(
        session,
        tool_definition_resolver=tool_definition_resolver,
    )


class _HistorySession:
    def __init__(self, manager: SessionManager) -> None:
        self.session_manager = manager

    def get_session_context(self):
        return self.session_manager.build_session_context()


__all__ = ["load_session_history_records"]
