from __future__ import annotations

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.interaction.intent import CodingUiIntent
from loushang.coding.interaction.tui_profile import (
    CodingLocalAction,
    build_coding_tui_host_profile,
)
from loushang.harnesstui.conversation.control import (
    ConversationRunControl,
    ConversationTextAction,
)
from loushang.harnesstui.conversation.host import (
    ConversationHostProfile,
    ConversationHostRoute,
)


def _profile(
    lifecycle: ConversationRunControl,
    traces: list[tuple[str, dict[str, object]]] | None = None,
) -> ConversationHostProfile[CodingUiIntent, CodingLocalAction]:
    sink = traces if traces is not None else []
    return build_coding_tui_host_profile(
        lifecycle=lifecycle,
        command_catalog=CodingCommandCatalog(session_commands=lambda: []),
        session_running=lambda: False,
        trace=lambda name, **data: sink.append((name, data)),
        now=lambda: 0.0,
    )


def _route(intent: CodingUiIntent, lifecycle: ConversationRunControl):
    return _profile(lifecycle).decide(intent, ConversationTextAction("input"))


def test_coding_tui_profile_preserves_running_input_policy() -> None:
    from loushang.coding.interaction.intent import (
        CommandSelectIntent,
        CommandsIntent,
        DebugIntent,
        FollowUpIntent,
        HotkeysIntent,
        ModelSelectIntent,
        ModelsIntent,
        PromptIntent,
        QuitIntent,
        SettingsIntent,
    )

    lifecycle = ConversationRunControl()
    lifecycle.begin_work()

    follow = _route(FollowUpIntent("later"), lifecycle)
    assert follow.route is ConversationHostRoute.FOLLOW_UP
    assert (follow.text, follow.source) == ("later", "command")
    assert _route(PromptIntent("steer"), lifecycle).route is ConversationHostRoute.STEER
    assert _route(DebugIntent(), lifecycle).route is ConversationHostRoute.STEER
    assert _route(QuitIntent(), lifecycle).route is ConversationHostRoute.DISPATCH

    local_cases = (
        (ModelSelectIntent(), CodingLocalAction.MODEL_SELECT),
        (ModelsIntent(), CodingLocalAction.MODELS),
        (HotkeysIntent(), CodingLocalAction.HOTKEYS),
        (SettingsIntent(), CodingLocalAction.SETTINGS),
        (CommandSelectIntent(), CodingLocalAction.COMMAND_SELECT),
        (CommandsIntent(), CodingLocalAction.COMMANDS),
    )
    for intent, action in local_cases:
        decision = _route(intent, lifecycle)
        assert decision.route is ConversationHostRoute.LOCAL
        assert decision.local is action


def test_coding_tui_profile_blocks_non_quit_input_while_abort_settles() -> None:
    from loushang.coding.interaction.intent import PromptIntent, QuitIntent

    lifecycle = ConversationRunControl()
    lifecycle.begin_work()
    lifecycle.mark_abort_requested()

    assert (
        _route(PromptIntent("new prompt"), lifecycle).route
        is ConversationHostRoute.ABORT_SETTLING
    )
    assert _route(QuitIntent(), lifecycle).route is ConversationHostRoute.DISPATCH


def test_coding_tui_profile_classifies_idle_dispatch_and_local_actions() -> None:
    from loushang.coding.interaction.intent import (
        BashIntent,
        DebugIntent,
        FollowUpIntent,
        PromptIntent,
        QuitIntent,
    )

    lifecycle = ConversationRunControl()

    debug = _route(DebugIntent(), lifecycle)
    assert debug.route is ConversationHostRoute.LOCAL
    assert debug.local is CodingLocalAction.DEBUG
    assert (
        _route(FollowUpIntent("later"), lifecycle).route
        is ConversationHostRoute.FOLLOW_UP
    )
    for intent in (PromptIntent("hello"), BashIntent("pwd"), QuitIntent()):
        assert _route(intent, lifecycle).route is ConversationHostRoute.DISPATCH


def test_coding_tui_profile_owns_prompt_trace_and_command_policy() -> None:
    from loushang.coding.interaction.intent import SettingsIntent

    traces: list[tuple[str, dict[str, object]]] = []
    profile = _profile(ConversationRunControl(), traces)

    assert profile.parse(ConversationTextAction("   ")) is None
    decision = profile.decide(SettingsIntent(), ConversationTextAction("/settings"))

    assert decision.local is CodingLocalAction.SETTINGS
    assert [name for name, _data in traces] == [
        "prompt.start",
        "prompt.ignored",
        "prompt.command",
    ]
