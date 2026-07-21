"""Coding binding for the shared conversation action controller."""

from __future__ import annotations

from typing import Any

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.interaction.intent import (
    AbortIntent,
    BashIntent,
    FollowUpIntent,
    PromptIntent,
    QuitIntent,
)
from loushang.harnesstui.conversation.controller import ConversationUiController
from loushang.observability import get_log

_LOG = get_log(__name__).bind(component="CodingUiController")


class CodingUiController(ConversationUiController):
    """Bind Coding's command catalog to the shared session action engine."""

    def __init__(
        self,
        *,
        session: Any,
        runtime: Any | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            session=session,
            runtime=runtime,
            verbose=verbose,
            command_catalog_factory=lambda current_session: CodingCommandCatalog(
                session_commands=(
                    current_session.list_commands
                    if callable(getattr(current_session, "list_commands", None))
                    else None
                )
            ),
            prompt_intent_type=PromptIntent,
            bash_intent_type=BashIntent,
            follow_up_intent_type=FollowUpIntent,
            abort_intent_type=AbortIntent,
            quit_intent_type=QuitIntent,
            problem_code_prefix="coding_ui",
            problem_logger=_LOG,
        )


__all__ = ["CodingUiController"]
