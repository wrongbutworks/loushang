from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from loushang.coding.ui.model import (
    iter_available_model_selections,
    model_label_from_selection,
)
from loushang.tui import CommandPalette, CompletionItem, CompletionProvider

ModelPaletteChooser = Callable[[CommandPalette], Awaitable[str | None] | str | None]


@dataclass(frozen=True)
class ModelChoice:
    label: str
    value: str
    selection: object
    endpoint_id: str = ""
    description: str = ""


@dataclass(frozen=True)
class _CurrentModelIdentity:
    label: str | None
    value: str | None


async def format_available_models(session: Any, *, query: str = "") -> str:
    choices = await available_model_choices(session)
    stripped_query = query.strip()
    if stripped_query:
        needle = stripped_query.lower()
        choices = [choice for choice in choices if _choice_matches_text(choice, needle)]
    current_value = await current_model_choice_value(session, choices=choices)

    if not choices:
        if stripped_query:
            return f"No models match: {stripped_query}"
        return "No models available."

    lines = ["Available models:"]
    for choice in choices:
        is_current = choice.value == current_value
        marker = "*" if is_current else " "
        suffix = " (current)" if is_current else ""
        lines.append(f"{marker} {_choice_display_label(choice)}{suffix}")
    return "\n".join(lines)


async def available_model_completion_provider(session: Any) -> CompletionProvider:
    items: list[CompletionItem] = []
    choices = await available_model_choices(session)
    current_value = await current_model_choice_value(session, choices=choices)
    for choice in choices:
        description = _choice_description(choice, current_value=current_value)
        items.append(CompletionItem(value=choice.value, label=choice.label, description=description))
    return CompletionProvider(tuple(items))


async def available_model_palette(session: Any, *, title: str = "Models") -> CommandPalette:
    provider = await available_model_completion_provider(session)
    return CommandPalette.from_completion_provider(provider, title=title)


async def select_available_model(session: Any, *, query: str = "", choose: ModelPaletteChooser | None = None) -> str:
    stripped_query = query.strip()
    if not stripped_query:
        if choose is not None:
            selected = await _maybe_await(choose(await available_model_palette(session, title="Models")))
            if selected is None:
                return "Model selection cancelled."
            return await select_available_model(session, query=selected)
        return await format_available_models(session)

    matches = _matching_model_choices(await available_model_choices(session), stripped_query)
    if not matches:
        return f"No models match: {stripped_query}"
    if len(matches) != 1:
        hint = (
            "Use /model <provider:endpoint:model> or choose one from the model list."
            if any(choice.endpoint_id for choice in matches)
            else "Use /model <full model> to select one."
        )
        return "\n".join(
            [
                "Multiple models match:",
                *(f"  {_choice_display_label(choice)}" for choice in matches),
                hint,
            ]
        )

    choice = matches[0]
    setter = getattr(session, "set_model", None)
    if not callable(setter):
        return "Model selection is not available."
    await _maybe_await(setter(choice.selection))
    return f"Model set: {_choice_display_label(choice)}"


async def available_model_choices(session: Any) -> list[ModelChoice]:
    current_identity = await _current_model_identity(session)
    detail_choices = _model_choices_from_details(await _available_model_details(session))
    selection_choices = [
        ModelChoice(label=label, value=label, selection=selection)
        for selection in await iter_available_model_selections(session)
        if (label := model_label_from_selection(selection)) is not None
    ]
    if detail_choices:
        detail_labels = {choice.label for choice in detail_choices}
        detail_values = {choice.value for choice in detail_choices}
        choices = [
            *detail_choices,
            *(
                choice
                for choice in selection_choices
                if choice.label not in detail_labels and choice.value not in detail_values
            ),
        ]
        return _current_choice_first(
            choices,
            current_value=_selected_current_choice_value(choices, current_identity),
        )
    return _current_choice_first(
        selection_choices,
        current_value=_selected_current_choice_value(selection_choices, current_identity),
    )


async def current_model_choice_value(session: Any, *, choices: list[ModelChoice] | None = None) -> str | None:
    model_choices = choices if choices is not None else await available_model_choices(session)
    return _selected_current_choice_value(model_choices, await _current_model_identity(session))


async def model_detail_descriptions_by_label(session: Any) -> dict[str, str]:
    getter = getattr(session, "get_available_model_details", None)
    if not callable(getter):
        return {}
    raw_details = await _maybe_await(getter())
    if not isinstance(raw_details, list | tuple):
        return {}
    descriptions: dict[str, str] = {}
    for detail in raw_details:
        label = model_label_from_selection(detail)
        description = _model_detail_description(detail)
        if label is not None and description:
            descriptions[label] = description
    return descriptions


def _matching_model_choices(choices: list[ModelChoice], query: str) -> list[ModelChoice]:
    needle = query.lower()
    exact_value = [choice for choice in choices if choice.value.lower() == needle]
    if exact_value:
        return exact_value
    labelled = [choice for choice in choices if _choice_matches_text(choice, needle)]
    exact_label = [choice for choice in labelled if choice.label.lower() == needle]
    return exact_label or labelled


async def _current_model_identity(session: Any) -> _CurrentModelIdentity:
    agent_model_identity = _model_identity_from_value(getattr(getattr(session, "agent", None), "model", None))
    if agent_model_identity.value is not None:
        return agent_model_identity
    getter = getattr(session, "get_model_selection", None)
    if not callable(getter):
        return _CurrentModelIdentity(label=None, value=None)
    selection = await _maybe_await(getter())
    return _model_identity_from_value(selection)


def _model_identity_from_value(selection: object | None) -> _CurrentModelIdentity:
    label = model_label_from_selection(selection)
    provider = _string_attr(selection, "provider_id", "provider", "providerId")
    endpoint_id = _string_attr(selection, "endpoint_id", "endpoint", "endpointId")
    model_id = _string_attr(selection, "id", "model_id", "modelId")
    value = (
        _model_choice_value(provider=provider, endpoint_id=endpoint_id, model_id=model_id, fallback=label or "")
        if provider and endpoint_id and model_id
        else None
    )
    return _CurrentModelIdentity(label=label, value=value)


def _selected_current_choice_value(
    choices: list[ModelChoice],
    current_identity: _CurrentModelIdentity,
) -> str | None:
    if current_identity.value is not None:
        for choice in choices:
            if choice.value == current_identity.value:
                return choice.value
    if current_identity.label is not None:
        for choice in choices:
            if choice.label == current_identity.label:
                return choice.value
    return None


def _current_choice_first(choices: list[ModelChoice], *, current_value: str | None) -> list[ModelChoice]:
    if current_value is None:
        return choices
    current = [choice for choice in choices if choice.value == current_value]
    if not current:
        return choices
    return [*current, *(choice for choice in choices if choice.value != current_value)]


async def _available_model_details(session: Any) -> list[object]:
    getter = getattr(session, "get_available_model_details", None)
    if not callable(getter):
        return []
    raw_details = await _maybe_await(getter())
    if not isinstance(raw_details, list | tuple):
        return []
    return list(raw_details)


def _model_choices_from_details(details: list[object]) -> list[ModelChoice]:
    choices: list[ModelChoice] = []
    seen: set[str] = set()
    for detail in details:
        label = model_label_from_selection(detail)
        if label is None:
            continue
        provider = _string_attr(detail, "provider_id", "provider", "providerId")
        endpoint_id = _string_attr(detail, "endpoint_id", "endpoint", "endpointId")
        model_id = _string_attr(detail, "id", "model_id", "modelId")
        value = _model_choice_value(provider=provider, endpoint_id=endpoint_id, model_id=model_id, fallback=label)
        if value in seen:
            continue
        seen.add(value)
        choices.append(
            ModelChoice(
                label=label,
                value=value,
                selection=detail,
                endpoint_id=endpoint_id or "",
                description=_model_detail_description(detail),
            )
        )
    return choices


def _model_choice_value(
    *,
    provider: str | None,
    endpoint_id: str | None,
    model_id: str | None,
    fallback: str,
) -> str:
    if provider and endpoint_id and model_id:
        return f"{provider}:{endpoint_id}:{model_id}"
    return fallback


def _choice_matches_text(choice: ModelChoice, needle: str) -> bool:
    return (
        needle in choice.label.lower()
        or needle in choice.value.lower()
        or bool(choice.endpoint_id and needle in choice.endpoint_id.lower())
        or bool(choice.description and needle in choice.description.lower())
    )


def _choice_description(choice: ModelChoice, *, current_value: str | None) -> str:
    parts: list[str] = []
    if choice.value == current_value:
        parts.append("current")
    if choice.endpoint_id:
        parts.append(f"endpoint: {choice.endpoint_id}")
    if choice.description:
        parts.append(choice.description)
    return " - ".join(parts)


def _choice_display_label(choice: ModelChoice) -> str:
    if choice.endpoint_id:
        return f"{choice.label} (endpoint: {choice.endpoint_id})"
    return choice.label


def _string_attr(item: object, *names: str) -> str | None:
    for name in names:
        if isinstance(item, Mapping):
            value = item.get(name)
        else:
            value = getattr(item, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _model_detail_description(detail: object) -> str:
    for name in ("name", "family", "alias"):
        value = getattr(detail, name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "available_model_choices",
    "available_model_completion_provider",
    "available_model_palette",
    "current_model_choice_value",
    "format_available_models",
    "ModelChoice",
    "ModelPaletteChooser",
    "model_detail_descriptions_by_label",
    "select_available_model",
]
