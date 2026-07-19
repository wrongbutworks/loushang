from __future__ import annotations

from enum import Enum

from loushang.coding.ui.intent import (
    CodingUiIntent,
    CommandSelectIntent,
    CommandsIntent,
    DebugIntent,
    FollowUpIntent,
    HotkeysIntent,
    ModelSelectIntent,
    ModelsIntent,
    QuitIntent,
    SettingsIntent,
)
from loushang.harnesstui.conversation.control import (
    ConversationRunControl as RunLifecycle,
)


class PromptRoute(Enum):
    ABORT_SETTLING = "abort_settling"
    COMMAND_SELECT = "command_select"
    COMMANDS = "commands"
    DEBUG = "debug"
    DISPATCH = "dispatch"
    FOLLOW_UP = "follow_up"
    HOTKEYS = "hotkeys"
    MODEL_SELECT = "model_select"
    MODELS = "models"
    SETTINGS = "settings"
    STEER = "steer"


def route_prompt_intent(intent: CodingUiIntent, lifecycle: RunLifecycle) -> PromptRoute:
    if lifecycle.abort_is_settling() and not isinstance(intent, QuitIntent):
        return PromptRoute.ABORT_SETTLING
    if isinstance(intent, CommandSelectIntent):
        return PromptRoute.COMMAND_SELECT
    if isinstance(intent, CommandsIntent):
        return PromptRoute.COMMANDS
    if isinstance(intent, ModelSelectIntent):
        return PromptRoute.MODEL_SELECT
    if isinstance(intent, ModelsIntent):
        return PromptRoute.MODELS
    if isinstance(intent, HotkeysIntent):
        return PromptRoute.HOTKEYS
    if isinstance(intent, SettingsIntent):
        return PromptRoute.SETTINGS
    if lifecycle.active and isinstance(intent, FollowUpIntent):
        return PromptRoute.FOLLOW_UP
    if lifecycle.active and not isinstance(intent, QuitIntent):
        return PromptRoute.STEER
    if isinstance(intent, DebugIntent):
        return PromptRoute.DEBUG
    if isinstance(intent, FollowUpIntent):
        return PromptRoute.FOLLOW_UP
    return PromptRoute.DISPATCH


__all__ = ["PromptRoute", "route_prompt_intent"]
