"""Coding model-policy adapter over AI values and Harness session operations."""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from dataclasses import dataclass

from loushang.ai.model import ModelSelection
from loushang.harness.session.model_selection import (
    ModelSelectionApplyResult,
    apply_session_model_selection,
    iter_available_model_selections,
)
from loushang.harness.session.model_selection import (
    ensure_usable_session_model as _ensure_usable_session_model,
)


@dataclass(frozen=True)
class PreferredModel:
    provider: str
    endpoint_id: str
    model_id: str


PREFERRED_CODING_MODELS = (
    PreferredModel("kimi-code", "kimi-code-anthropic", "kimi-for-coding"),
)


async def apply_model_selection(
    session: object,
    selection: object,
    *,
    settings_manager: object | None = None,
    scope: str = "global",
) -> ModelSelectionApplyResult:
    resolved_settings_manager = (
        settings_manager
        if settings_manager is not None
        else getattr(session, "settings_manager", None)
    )
    persist = getattr(resolved_settings_manager, "set_default_model", None)
    if not callable(persist):
        return await apply_session_model_selection(session, selection)

    def persist_default(model: ModelSelection) -> object:
        return persist(model, scope=scope)

    return await apply_session_model_selection(
        session,
        selection,
        persist=persist_default,
    )


async def ensure_usable_session_model(session: object) -> ModelSelection | None:
    return await _ensure_usable_session_model(session, candidates=_model_candidates)


def persistence_warning_message(result: ModelSelectionApplyResult) -> str | None:
    if result.persistence_error is None:
        return None
    message = (
        str(result.persistence_error).strip()
        or result.persistence_error.__class__.__name__
    )
    return f"saving the default failed: {message}"


async def _model_candidates(session: object) -> Iterable[object]:
    details = await _available_model_details(session)
    preferred_details = _preferred_available_model_details(details)
    if preferred_details:
        return preferred_details
    selections = await iter_available_model_selections(session)
    preferred_selection = _preferred_available_selection(selections)
    return [preferred_selection] if preferred_selection is not None else selections


async def _available_model_details(session: object) -> list[object]:
    getter = getattr(session, "get_available_model_details", None)
    if not callable(getter):
        return []
    values = getter()
    values = await values if inspect.isawaitable(values) else values
    return list(values) if isinstance(values, Iterable) else []


def _preferred_available_model_details(details: Iterable[object]) -> list[object]:
    matches: list[object] = []
    for preferred in PREFERRED_CODING_MODELS:
        for detail in details:
            if _matches_preferred_model_detail(detail, preferred):
                matches.append(detail)
                break
    return matches


def _preferred_available_selection(
    selections: Iterable[ModelSelection],
) -> ModelSelection | None:
    for preferred in PREFERRED_CODING_MODELS:
        for selection in selections:
            if (
                selection.provider == preferred.provider
                and selection.model_id == preferred.model_id
            ):
                return selection
    return None


def _matches_preferred_model_detail(detail: object, preferred: PreferredModel) -> bool:
    return (
        _string_attr(detail, "provider", "provider_id") == preferred.provider
        and _string_attr(detail, "endpoint", "endpoint_id") == preferred.endpoint_id
        and _string_attr(detail, "model_id", "id") == preferred.model_id
    )


def _string_attr(value: object, *names: str) -> str | None:
    for name in names:
        raw_value = getattr(value, name, None)
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return None


__all__ = [
    "ModelSelectionApplyResult",
    "PREFERRED_CODING_MODELS",
    "PreferredModel",
    "apply_model_selection",
    "ensure_usable_session_model",
    "persistence_warning_message",
]
