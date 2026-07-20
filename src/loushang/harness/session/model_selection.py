"""Optional AI-backed model selection operations for product sessions."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from loushang.ai.model import (
    ModelSelection,
    is_usable_model_selection,
    normalize_model_selection,
)

ModelCandidates = Callable[[object], Iterable[object] | Awaitable[Iterable[object]]]
PersistModelSelection = Callable[[ModelSelection], object]


@dataclass(frozen=True)
class ModelSelectionApplyResult:
    selection: ModelSelection
    persisted: bool = False
    persistence_error: Exception | None = None


async def apply_session_model_selection(
    session: object,
    selection: object,
    *,
    persist: PersistModelSelection | None = None,
) -> ModelSelectionApplyResult:
    """Apply a model on a bound session and optionally persist its selection."""

    normalized = normalize_model_selection(selection)
    if normalized is None:
        raise ValueError("Model selection requires provider and model id.")
    setter = getattr(session, "set_model", None)
    if not callable(setter):
        raise RuntimeError("Model selection is not available.")
    await _maybe_await(setter(normalized))
    if persist is None:
        return ModelSelectionApplyResult(selection=normalized)
    try:
        await _maybe_await(persist(normalized))
    except Exception as error:
        return ModelSelectionApplyResult(selection=normalized, persistence_error=error)
    return ModelSelectionApplyResult(selection=normalized, persisted=True)


async def get_session_model_selection(session: object) -> ModelSelection | None:
    getter = getattr(session, "get_model_selection", None)
    if not callable(getter):
        return None
    return normalize_model_selection(await _maybe_await(getter()))


async def iter_available_model_selections(session: object) -> list[ModelSelection]:
    getter = getattr(session, "get_available_models", None)
    if not callable(getter):
        return []
    return _dedupe_model_selections(await _maybe_await(getter()))


async def iter_scoped_model_selections(session: object) -> list[ModelSelection]:
    raw_models = getattr(session, "scopedModels", None)
    if raw_models is None:
        getter = getattr(session, "get_scoped_models", None)
        raw_models = await _maybe_await(getter()) if callable(getter) else None
    if not isinstance(raw_models, Iterable):
        return []
    return _dedupe_model_selections(
        value.get("model", value) if isinstance(value, Mapping) else value
        for value in raw_models
    )


async def ensure_usable_session_model(
    session: object,
    *,
    candidates: ModelCandidates | None = None,
) -> ModelSelection | None:
    """Ensure a usable model using a product-provided candidate policy."""

    current = await get_session_model_selection(session)
    if is_usable_model_selection(current):
        return current
    raw_candidates = (
        await _maybe_await(candidates(session))
        if candidates is not None
        else await iter_available_model_selections(session)
    )
    setter = getattr(session, "set_model", None)
    for candidate in raw_candidates:
        normalized = normalize_model_selection(candidate)
        if normalized is None or not is_usable_model_selection(normalized):
            continue
        if not callable(setter):
            return normalized
        try:
            await _maybe_await(setter(candidate))
        except (RuntimeError, ValueError):
            continue
        return await get_session_model_selection(session) or normalized
    return None


def _dedupe_model_selections(values: object) -> list[ModelSelection]:
    if not isinstance(values, Iterable):
        return []
    selections: list[ModelSelection] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_value in values:
        selection = normalize_model_selection(raw_value)
        if selection is None or not is_usable_model_selection(selection):
            continue
        key = (selection.provider, selection.endpoint_id or "", selection.model_id)
        if key not in seen:
            seen.add(key)
            selections.append(selection)
    return selections


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


__all__ = [
    "ModelCandidates",
    "ModelSelectionApplyResult",
    "PersistModelSelection",
    "apply_session_model_selection",
    "ensure_usable_session_model",
    "get_session_model_selection",
    "iter_available_model_selections",
    "iter_scoped_model_selections",
]
