from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any

from loushang.ai.model import model_label_from_selection
from loushang.coding.model_selection import (
    apply_model_selection,
    persistence_warning_message,
)
from loushang.harness.session.model_selection import iter_available_model_selections
from loushang.harnesstui.selection.binding import (
    model_choices_from_details,
    model_identity_from_value,
)
from loushang.harnesstui.selection.catalog import (
    ModelChoice,
    ModelChoiceIdentity,
    merge_model_choice_sources,
    resolve_current_model_choice_value,
)
from loushang.harnesstui.selection.interaction import (
    ModelInteractionChooser as ModelPaletteChooser,
)
from loushang.harnesstui.selection.runtime import (
    ModelSelectionViewPort,
)
from loushang.harnesstui.selection.runtime import (
    available_model_completion_provider as _available_model_completion_provider,
)
from loushang.harnesstui.selection.runtime import (
    format_available_models as _format_available_models,
)
from loushang.harnesstui.selection.runtime import (
    select_available_model as _select_available_model,
)
from loushang.tui import CompletionProvider


async def format_available_models(session: Any, *, query: str = "") -> str:
    return await _format_available_models(_CodingModelSelectionPort(session), query=query)


async def available_model_completion_provider(session: Any) -> CompletionProvider:
    return await _available_model_completion_provider(_CodingModelSelectionPort(session))


async def select_available_model(
    session: Any,
    *,
    query: str = "",
    choose: ModelPaletteChooser | None = None,
    settings_manager: object | None = None,
) -> str:
    return await _select_available_model(
        _CodingModelSelectionPort(session, settings_manager=settings_manager),
        query=query,
        choose=choose,
        persistence_warning=lambda result: persistence_warning_message(result),
    )


class _CodingModelSelectionPort(ModelSelectionViewPort):
    """Bind Coding session acquisition and persistence to shared TUI runtime."""

    def __init__(
        self,
        session: Any,
        *,
        settings_manager: object | None = None,
    ) -> None:
        self._session = session
        self._settings_manager = settings_manager

    async def available_choices(self) -> list[ModelChoice]:
        return await available_model_choices(self._session)

    async def current_value(self, choices: Sequence[ModelChoice]) -> str | None:
        return await current_model_choice_value(self._session, choices=choices)

    async def apply_selection(self, selection: object) -> object:
        return await apply_model_selection(
            self._session,
            selection,
            settings_manager=self._settings_manager,
        )


async def available_model_choices(session: Any) -> list[ModelChoice]:
    current_identity = await _current_model_identity(session)
    detail_choices = model_choices_from_details(await _available_model_details(session))
    selection_choices = [
        ModelChoice(label=label, value=label, selection=selection)
        for selection in await iter_available_model_selections(session)
        if (label := model_label_from_selection(selection)) is not None
    ]
    return merge_model_choice_sources(
        detail_choices,
        selection_choices,
        current_identity=current_identity,
    )


async def current_model_choice_value(
    session: Any, *, choices: Sequence[ModelChoice] | None = None
) -> str | None:
    model_choices = (
        choices if choices is not None else await available_model_choices(session)
    )
    return resolve_current_model_choice_value(
        model_choices, await _current_model_identity(session)
    )


async def _current_model_identity(session: Any) -> ModelChoiceIdentity:
    try:
        agent = session.agent
    except AttributeError:
        agent = None
    try:
        agent_model = agent.model
    except AttributeError:
        agent_model = None
    agent_model_identity = model_identity_from_value(agent_model)
    if agent_model_identity.value is not None:
        return agent_model_identity
    try:
        getter = session.get_model_selection
    except AttributeError:
        return ModelChoiceIdentity()
    if not callable(getter):
        return ModelChoiceIdentity()
    selection = await _maybe_await(getter())
    return model_identity_from_value(selection)


async def _available_model_details(session: Any) -> list[object]:
    try:
        getter = session.get_available_model_details
    except AttributeError:
        return []
    if not callable(getter):
        return []
    raw_details = await _maybe_await(getter())
    if not isinstance(raw_details, list | tuple):
        return []
    return list(raw_details)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "available_model_choices",
    "available_model_completion_provider",
    "current_model_choice_value",
    "format_available_models",
    "ModelChoice",
    "ModelPaletteChooser",
    "select_available_model",
]
