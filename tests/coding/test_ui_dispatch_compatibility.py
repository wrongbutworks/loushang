from __future__ import annotations

from typing import Protocol


def test_prompt_dispatch_compatibility_exports_share_neutral_owner() -> None:
    from loushang.coding.ui.prompt_dispatch import (
        Lifecycle,
        PromptDispatchOutcome,
    )
    from loushang.harnesstui.conversation.dispatch import (
        ConversationDispatchOutcome,
        DispatchLifecycle,
    )

    assert PromptDispatchOutcome is ConversationDispatchOutcome
    assert Lifecycle is DispatchLifecycle


def test_prompt_result_renderer_compatibility_export_shares_neutral_owner() -> (
    None
):
    from loushang.coding.ui.prompt_result import Renderer
    from loushang.harnesstui.conversation.dispatch import ResultRenderer

    assert Renderer is ResultRenderer


def test_coding_event_renderer_remains_a_real_protocol_class() -> None:
    from loushang.coding.ui.event_stream import EventRenderer

    assert isinstance(EventRenderer, type)
    assert issubclass(EventRenderer, Protocol)
    assert EventRenderer._is_protocol is True
