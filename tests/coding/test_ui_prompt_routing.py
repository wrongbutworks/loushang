from __future__ import annotations


def test_prompt_routing_keeps_running_inputs_pi_style() -> None:
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
    from loushang.coding.ui.prompt_routing import PromptRoute, route_prompt_intent
    from loushang.harnesstui.conversation.control import ConversationRunControl

    lifecycle = ConversationRunControl()
    lifecycle.begin_work()

    assert route_prompt_intent(FollowUpIntent("later"), lifecycle) is PromptRoute.FOLLOW_UP
    assert route_prompt_intent(PromptIntent("steer"), lifecycle) is PromptRoute.STEER
    assert route_prompt_intent(DebugIntent(), lifecycle) is PromptRoute.STEER
    assert route_prompt_intent(ModelSelectIntent(), lifecycle) is PromptRoute.MODEL_SELECT
    assert route_prompt_intent(ModelsIntent(), lifecycle) is PromptRoute.MODELS
    assert route_prompt_intent(HotkeysIntent(), lifecycle) is PromptRoute.HOTKEYS
    assert route_prompt_intent(SettingsIntent(), lifecycle) is PromptRoute.SETTINGS
    assert route_prompt_intent(CommandSelectIntent(), lifecycle) is PromptRoute.COMMAND_SELECT
    assert route_prompt_intent(CommandsIntent(), lifecycle) is PromptRoute.COMMANDS
    assert route_prompt_intent(QuitIntent(), lifecycle) is PromptRoute.DISPATCH

def test_prompt_routing_blocks_non_quit_inputs_while_abort_settles() -> None:
    from loushang.coding.interaction.intent import FollowUpIntent, PromptIntent, QuitIntent
    from loushang.coding.ui.prompt_routing import PromptRoute, route_prompt_intent
    from loushang.harnesstui.conversation.control import ConversationRunControl

    lifecycle = ConversationRunControl()
    lifecycle.begin_work()
    lifecycle.mark_abort_requested()

    assert route_prompt_intent(PromptIntent("new prompt"), lifecycle) is PromptRoute.ABORT_SETTLING
    assert route_prompt_intent(FollowUpIntent("later"), lifecycle) is PromptRoute.ABORT_SETTLING
    assert route_prompt_intent(QuitIntent(), lifecycle) is PromptRoute.DISPATCH


def test_prompt_routing_dispatches_idle_intents_except_debug_and_follow_up() -> None:
    from loushang.coding.interaction.intent import (
        BashIntent,
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
    from loushang.coding.ui.prompt_routing import PromptRoute, route_prompt_intent
    from loushang.harnesstui.conversation.control import ConversationRunControl

    lifecycle = ConversationRunControl()

    assert route_prompt_intent(DebugIntent(), lifecycle) is PromptRoute.DEBUG
    assert route_prompt_intent(ModelSelectIntent(), lifecycle) is PromptRoute.MODEL_SELECT
    assert route_prompt_intent(ModelsIntent(), lifecycle) is PromptRoute.MODELS
    assert route_prompt_intent(HotkeysIntent(), lifecycle) is PromptRoute.HOTKEYS
    assert route_prompt_intent(SettingsIntent(), lifecycle) is PromptRoute.SETTINGS
    assert route_prompt_intent(CommandSelectIntent(), lifecycle) is PromptRoute.COMMAND_SELECT
    assert route_prompt_intent(CommandsIntent(), lifecycle) is PromptRoute.COMMANDS
    assert route_prompt_intent(FollowUpIntent("later"), lifecycle) is PromptRoute.FOLLOW_UP
    assert route_prompt_intent(PromptIntent("hello"), lifecycle) is PromptRoute.DISPATCH
    assert route_prompt_intent(BashIntent("pwd"), lifecycle) is PromptRoute.DISPATCH
    assert route_prompt_intent(QuitIntent(), lifecycle) is PromptRoute.DISPATCH
