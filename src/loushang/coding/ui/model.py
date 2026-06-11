from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from loushang.coding.types import ModelSelection

T = TypeVar("T")


@dataclass(frozen=True)
class PreferredModel:
    provider: str
    endpoint_id: str
    model_id: str


PREFERRED_CODING_MODELS = (
    PreferredModel("moonshot", "kimi-code-anthropic", "kimi-for-coding"),
    PreferredModel("moonshot", "openai-completions:cn:coding", "kimi-for-coding"),
)


def normalize_model_selection(selection: object | None) -> ModelSelection | None:
    if selection is None:
        return None
    provider = _string_attr(selection, "provider", "provider_id", "providerId")
    model_id = _string_attr(selection, "model_id", "modelId", "id")
    endpoint_id = _string_attr(selection, "endpoint_id", "endpoint", "endpointId")
    if provider is None or model_id is None:
        return None
    return ModelSelection(provider=provider, model_id=model_id, endpoint_id=endpoint_id)


def is_usable_model_selection(selection: object | None) -> bool:
    normalized = normalize_model_selection(selection)
    if normalized is None:
        return False
    return _is_usable_value(normalized.provider) and _is_usable_value(normalized.model_id)


def model_label_from_selection(selection: object | None) -> str | None:
    normalized = normalize_model_selection(selection)
    if normalized is None or not _is_usable_value(normalized.provider) or not _is_usable_value(normalized.model_id):
        return None
    return f"{normalized.provider}/{normalized.model_id}"


def current_model_first(
    items: Iterable[T],
    *,
    current_label: str | None,
    label_of: Callable[[T], str | None],
) -> list[T]:
    ordered = list(items)
    if current_label is None:
        return ordered
    current = [item for item in ordered if label_of(item) == current_label]
    if not current:
        return ordered
    return [*current, *(item for item in ordered if label_of(item) != current_label)]


async def get_session_model_selection(session: Any) -> ModelSelection | None:
    getter = getattr(session, "get_model_selection", None)
    if not callable(getter):
        return None
    return normalize_model_selection(await _maybe_await(getter()))


async def iter_available_model_selections(session: Any) -> list[ModelSelection]:
    getter = getattr(session, "get_available_models", None)
    if not callable(getter):
        return []
    raw_models = await _maybe_await(getter())
    if not isinstance(raw_models, Iterable):
        return []
    selections: list[ModelSelection] = []
    seen: set[tuple[str, str]] = set()
    for raw_model in raw_models:
        selection = normalize_model_selection(raw_model)
        if selection is None or not is_usable_model_selection(selection):
            continue
        key = (selection.provider, selection.endpoint_id or "", selection.model_id)
        if key in seen:
            continue
        seen.add(key)
        selections.append(selection)
    return selections


async def iter_scoped_model_selections(session: Any) -> list[ModelSelection]:
    raw_models = await _session_scoped_models(session)
    if not isinstance(raw_models, Iterable):
        return []
    selections: list[ModelSelection] = []
    seen: set[tuple[str, str]] = set()
    for raw_model in raw_models:
        scoped_model = _scoped_model_value(raw_model)
        selection = normalize_model_selection(scoped_model)
        if selection is None or not is_usable_model_selection(selection):
            continue
        key = (selection.provider, selection.endpoint_id or "", selection.model_id)
        if key in seen:
            continue
        seen.add(key)
        selections.append(selection)
    return selections


async def ensure_usable_session_model(session: Any) -> ModelSelection | None:
    current = await get_session_model_selection(session)
    if is_usable_model_selection(current):
        return current

    setter = getattr(session, "set_model", None)
    candidates = await _model_candidates(session)
    if not candidates:
        return None
    if not callable(setter):
        return normalize_model_selection(candidates[0])

    for candidate in candidates:
        try:
            await _maybe_await(setter(candidate))
        except (RuntimeError, ValueError):
            continue
        updated = await get_session_model_selection(session)
        return normalize_model_selection(updated) or normalize_model_selection(candidate)
    return None


async def _model_candidates(session: Any) -> list[object]:
    details = await _available_model_details(session)
    preferred_details = _preferred_available_model_details(details)
    if preferred_details:
        return preferred_details

    selections = await iter_available_model_selections(session)
    preferred_selection = _preferred_available_selection(selections)
    if preferred_selection is not None:
        return [preferred_selection]
    return list(selections)


async def _available_model_details(session: Any) -> list[object]:
    getter = getattr(session, "get_available_model_details", None)
    if not callable(getter):
        return []
    raw_details = await _maybe_await(getter())
    if not isinstance(raw_details, Iterable):
        return []
    return list(raw_details)


def _preferred_available_model_details(details: list[object]) -> list[object]:
    matches: list[object] = []
    for preferred in PREFERRED_CODING_MODELS:
        for detail in details:
            if _matches_preferred_model_detail(detail, preferred):
                matches.append(detail)
                break
    return matches


def _preferred_available_selection(selections: list[ModelSelection]) -> ModelSelection | None:
    for preferred in PREFERRED_CODING_MODELS:
        for selection in selections:
            if selection.provider == preferred.provider and selection.model_id == preferred.model_id:
                return selection
    return None


def _matches_preferred_model_detail(detail: object, preferred: PreferredModel) -> bool:
    provider = _string_attr(detail, "provider", "provider_id")
    endpoint_id = _string_attr(detail, "endpoint", "endpoint_id")
    model_id = _string_attr(detail, "model_id", "id")
    return provider == preferred.provider and endpoint_id == preferred.endpoint_id and model_id == preferred.model_id


def _string_attr(value: object, *names: str) -> str | None:
    for name in names:
        if isinstance(value, Mapping):
            raw_value = value.get(name)
        else:
            raw_value = getattr(value, name, None)
        if isinstance(raw_value, str) and raw_value:
            return raw_value
    return None


async def _session_scoped_models(session: Any) -> object | None:
    raw_models = getattr(session, "scopedModels", None)
    if raw_models is not None:
        return raw_models
    getter = getattr(session, "get_scoped_models", None)
    if callable(getter):
        return await _maybe_await(getter())
    return None


def _scoped_model_value(value: object) -> object:
    if isinstance(value, Mapping):
        return value.get("model", value)
    return value


def _is_usable_value(value: str) -> bool:
    return value.strip().lower() not in {"", "unknown"}


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "PREFERRED_CODING_MODELS",
    "PreferredModel",
    "ensure_usable_session_model",
    "current_model_first",
    "get_session_model_selection",
    "is_usable_model_selection",
    "iter_available_model_selections",
    "iter_scoped_model_selections",
    "model_label_from_selection",
    "normalize_model_selection",
]
