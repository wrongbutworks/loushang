from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loushang.coding.ui.model import (
    ensure_usable_session_model,
    get_session_model_selection,
    model_label_from_selection,
)
from loushang.coding.ui.session_view import (
    git_branch,
    project_label,
    session_cwd,
    session_label,
    session_observability_id,
)


@dataclass(frozen=True)
class CodingTuiStartupSnapshot:
    model_label: str | None
    cwd: str
    branch: str | None
    project_label: str
    session_label: str | None
    session_observability_id: str | None


async def load_coding_tui_startup_snapshot(*, runtime: Any, session: Any) -> CodingTuiStartupSnapshot:
    await ensure_usable_session_model(session)
    model_label = model_label_from_selection(await get_session_model_selection(session))
    cwd = session_cwd(session=session, runtime=runtime)
    return CodingTuiStartupSnapshot(
        model_label=model_label,
        cwd=cwd,
        branch=git_branch(cwd),
        project_label=project_label(cwd),
        session_label=session_label(session),
        session_observability_id=session_observability_id(session),
    )


__all__ = ["CodingTuiStartupSnapshot", "load_coding_tui_startup_snapshot"]
