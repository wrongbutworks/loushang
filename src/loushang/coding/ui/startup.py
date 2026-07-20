from __future__ import annotations

from typing import Any

from loushang.ai.model import model_label_from_selection
from loushang.coding.model_selection import (
    ensure_usable_session_model,
)
from loushang.coding.presentation.session import (
    git_branch,
    session_cwd,
    session_label,
    session_observability_id,
)
from loushang.harness.session.model_selection import get_session_model_selection
from loushang.harnesstui.conversation.startup import (
    ConversationStartupView,
    build_conversation_startup_view,
)


async def load_coding_tui_startup_view(
    *, runtime: Any, session: Any
) -> ConversationStartupView:
    await ensure_usable_session_model(session)
    model_label = model_label_from_selection(await get_session_model_selection(session))
    cwd = session_cwd(session=session, runtime=runtime)
    return build_conversation_startup_view(
        model_label=model_label,
        cwd=cwd,
        branch=git_branch(cwd),
        session_label=session_label(session),
        session_observability_id=session_observability_id(session),
    )


__all__ = ["load_coding_tui_startup_view"]
