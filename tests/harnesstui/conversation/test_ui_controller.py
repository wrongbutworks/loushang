from __future__ import annotations

import asyncio
from types import SimpleNamespace

from loushang.harness.commands import CommandEffectKind
from loushang.harness.host.types import HostActionResult
from loushang.harnesstui.conversation.controller import (
    build_standard_conversation_ui_controller,
)
from loushang.harnesstui.conversation.intents import PromptIntent


def test_conversation_ui_controller_routes_actions_to_runtime_current_session() -> None:
    prompts: list[tuple[str, str]] = []
    followups: list[tuple[str, str]] = []

    class Session:
        def __init__(self, name: str) -> None:
            self.name = name

        async def prompt(self, text: str) -> None:
            prompts.append((self.name, text))

        async def follow_up(self, text: str) -> None:
            followups.append((self.name, text))

    initial = Session("initial")
    current = Session("current")
    runtime = SimpleNamespace(current_session=current)
    controller = build_standard_conversation_ui_controller(
        session=initial,
        runtime=runtime,
    )

    asyncio.run(controller.dispatch(PromptIntent("hello")))
    asyncio.run(controller.follow_up("later"))

    assert prompts == [("current", "hello")]
    assert followups == [("current", "later")]


def test_conversation_ui_controller_resolves_session_command_on_current_session() -> (
    None
):
    calls: list[tuple[str, str, str]] = []

    class Session:
        def __init__(self, name: str) -> None:
            self.name = name

        async def execute_command_async(self, command: str, args: str):
            calls.append((self.name, command, args))
            return SimpleNamespace(result={"status": "ok", "message": "restored"})

    class Catalog:
        def __init__(self, session: Session) -> None:
            calls.append(("catalog", session.name, ""))

        def effect_for_route(self, _route: str, _intent: object):
            return SimpleNamespace(
                kind=CommandEffectKind.SESSION,
                command=SimpleNamespace(source="builtin"),
                payload={"invocation_name": "/resume", "args": "session-2"},
            )

    initial = Session("initial")
    current = Session("current")
    controller = build_standard_conversation_ui_controller(
        session=initial,
        runtime=SimpleNamespace(current_session=current),
        command_catalog_factory=Catalog,
    )

    result = asyncio.run(controller.dispatch(PromptIntent("/resume session-2")))

    assert isinstance(result, HostActionResult)
    assert result.status_message == "restored"
    assert calls == [
        ("catalog", "current", ""),
        ("current", "/resume", "session-2"),
    ]
