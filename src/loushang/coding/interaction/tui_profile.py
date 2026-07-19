from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum

from loushang.coding.commands.catalog import CodingCommandCatalog
from loushang.coding.interaction.intent import (
    BashIntent,
    CodingUiIntent,
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
    parse_prompt_intent,
)
from loushang.harnesstui.conversation.action_presentation import (
    ConversationActionPresentationCopy,
)
from loushang.harnesstui.conversation.control import (
    ConversationRunControl,
    ConversationTextAction,
)
from loushang.harnesstui.conversation.host import (
    ConversationHostDecision,
    ConversationHostProfile,
    ConversationHostRoute,
)
from loushang.harnesstui.conversation.info import ConversationInfoPresenter
from loushang.harnesstui.conversation.run_context import TraceFn


class CodingLocalAction(Enum):
    DEBUG = "debug"
    MODEL_SELECT = "model_select"
    MODELS = "models"
    COMMAND_SELECT = "command_select"
    COMMANDS = "commands"
    HOTKEYS = "hotkeys"
    SETTINGS = "settings"


_LOCAL_INTENTS = {
    CommandSelectIntent: CodingLocalAction.COMMAND_SELECT,
    CommandsIntent: CodingLocalAction.COMMANDS,
    ModelSelectIntent: CodingLocalAction.MODEL_SELECT,
    ModelsIntent: CodingLocalAction.MODELS,
    HotkeysIntent: CodingLocalAction.HOTKEYS,
    SettingsIntent: CodingLocalAction.SETTINGS,
}


CODING_SCREEN_ACTION_COPY = ConversationActionPresentationCopy(
    dispatch_failure_status=lambda message: f"Request failed: {message}",
    steer_failure_status=lambda message: f"Steering failed: {message}",
    follow_up_failure_status=lambda message: f"Follow-up failed: {message}",
)


@dataclass(frozen=True, slots=True)
class CodingTuiProfile:
    """Coding policy projected onto the product-neutral conversation host."""

    lifecycle: ConversationRunControl
    command_catalog: CodingCommandCatalog
    session_running: Callable[[], bool]
    trace: TraceFn

    def host_profile(
        self,
        *,
        now: Callable[[], float],
    ) -> ConversationHostProfile[CodingUiIntent, CodingLocalAction]:
        return ConversationHostProfile(
            parse=self.parse,
            decide=self.decide,
            is_exit=lambda intent: isinstance(intent, QuitIntent),
            now=now,
        )

    def parse(self, action: ConversationTextAction) -> CodingUiIntent | None:
        self.trace(
            "prompt.start",
            active_run=self.lifecycle.active,
            active_run_id=self.lifecycle.active_id,
            aborted_run_id=self.lifecycle.aborted_id,
            session_running=self.session_running(),
            text_len=len(action.text),
        )
        intent = parse_prompt_intent(action.text)
        if intent is None:
            self.trace("prompt.ignored", reason="empty")
        return intent

    def decide(
        self,
        intent: CodingUiIntent,
        _action: ConversationTextAction,
    ) -> ConversationHostDecision[CodingLocalAction]:
        if self.lifecycle.abort_is_settling() and not isinstance(intent, QuitIntent):
            self.trace(
                "prompt.ignored",
                reason="abort_in_progress",
                active_run_id=self.lifecycle.active_id,
            )
            return ConversationHostDecision(ConversationHostRoute.ABORT_SETTLING)
        local_action = None
        for intent_type, action in _LOCAL_INTENTS.items():
            if isinstance(intent, intent_type):
                local_action = action
                break
        if local_action is not None:
            return self._local_decision(local_action, intent)
        if isinstance(intent, FollowUpIntent):
            return ConversationHostDecision(
                ConversationHostRoute.FOLLOW_UP,
                text=intent.text,
                source="command",
            )
        if self.lifecycle.active and not isinstance(intent, QuitIntent):
            return ConversationHostDecision(ConversationHostRoute.STEER)
        if isinstance(intent, DebugIntent):
            return self._local_decision(CodingLocalAction.DEBUG, intent)
        return ConversationHostDecision(ConversationHostRoute.DISPATCH)

    def _local_decision(
        self,
        action: CodingLocalAction,
        intent: CodingUiIntent,
    ) -> ConversationHostDecision[CodingLocalAction]:
        effect = self.command_catalog.effect_for_route(action, intent)
        if effect is not None:
            self.trace(
                "prompt.command",
                route=action.value,
                command_id=effect.command.id,
                command_name=effect.command.name,
                effect=effect.kind.value,
            )
        return ConversationHostDecision(ConversationHostRoute.LOCAL, local=action)


_PRESENTATION = {
    CodingLocalAction.MODEL_SELECT: ("Model", "model:select", False),
    CodingLocalAction.MODELS: ("Models", "models:show", True),
    CodingLocalAction.COMMAND_SELECT: ("Command", "command:select", False),
    CodingLocalAction.COMMANDS: ("Commands", "commands:show", True),
    CodingLocalAction.HOTKEYS: ("Hotkeys", "hotkeys:show", True),
    CodingLocalAction.SETTINGS: ("Settings", "settings:show", False),
}


@dataclass(frozen=True, slots=True)
class CodingTuiPorts:
    """Coding-only local actions supplied to the shared host."""

    debug: Callable[[DebugIntent], Awaitable[int | None]]
    model_select: Callable[[str], Awaitable[str]]
    models: Callable[[str], Awaitable[str]]
    command_select: Callable[[str], Awaitable[str]]
    commands: Callable[[str], Awaitable[str]]
    hotkeys: Callable[[], str]
    settings_text: Callable[[], str]
    info: ConversationInfoPresenter

    async def local(
        self,
        _text_action: ConversationTextAction,
        intent: CodingUiIntent,
        action: CodingLocalAction | None,
    ) -> int | None:
        if action is CodingLocalAction.DEBUG and isinstance(intent, DebugIntent):
            return await self.debug(intent)
        if action is None:
            return None
        if action is CodingLocalAction.HOTKEYS:
            text = self.hotkeys()
        elif action is CodingLocalAction.SETTINGS:
            text = self.settings_text()
        else:
            text = await getattr(self, action.value)(getattr(intent, "query", ""))
        title, label, modal = _PRESENTATION[action]
        await self.info.show(title, text, label=label, modal=modal)
        return None


def is_coding_work_intent(intent: CodingUiIntent) -> bool:
    return isinstance(intent, PromptIntent | BashIntent)
