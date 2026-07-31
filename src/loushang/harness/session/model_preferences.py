"""Product-neutral preferred-model candidate selection helpers."""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from loushang.ai.model import ModelSelection
from loushang.harness.session.model_selection import (
    iter_available_model_selections,
)


@dataclass(frozen=True)
class PreferredModel:
    """A stable model identity a Product may use for candidate ordering."""

    provider: str
    endpoint_id: str | None
    model_id: str


async def preferred_model_candidates(
    session: object,
    preferred_models: Sequence[PreferredModel],
) -> list[object]:
    """Return preferred available details, then preferred/model selections."""

    details = await available_model_details(session)
    preferred_details = preferred_model_details(details, preferred_models)
    if preferred_details:
        return preferred_details
    selections = await iter_available_model_selections(session)
    preferred_selection = preferred_model_selection(selections, preferred_models)
    if preferred_selection is not None:
        return [preferred_selection]
    candidates: list[object] = list(selections)
    return candidates


async def available_model_details(session: object) -> list[object]:
    getter = getattr(session, "get_available_model_details", None)
    if not callable(getter):
        return []
    values = getter()
    values = await values if inspect.isawaitable(values) else values
    return list(values) if isinstance(values, Iterable) else []


def preferred_model_details(
    details: Iterable[object],
    preferred_models: Sequence[PreferredModel],
) -> list[object]:
    values = list(details)
    matches: list[object] = []
    for preferred in preferred_models:
        for detail in values:
            if _matches_preferred_model_detail(detail, preferred):
                matches.append(detail)
                break
    return matches


def preferred_model_selection(
    selections: Iterable[ModelSelection],
    preferred_models: Sequence[PreferredModel],
) -> ModelSelection | None:
    values = list(selections)
    for preferred in preferred_models:
        for selection in values:
            if (
                selection.provider == preferred.provider
                and selection.model_id == preferred.model_id
            ):
                return selection
    return None


def persistence_warning_message(result: object) -> str | None:
    """Format a non-fatal default-model persistence failure."""

    error = getattr(result, "persistence_error", None)
    if error is None:
        return None
    message = str(error).strip() or error.__class__.__name__
    return f"saving the default failed: {message}"


def _matches_preferred_model_detail(
    detail: object,
    preferred: PreferredModel,
) -> bool:
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
    "PreferredModel",
    "available_model_details",
    "preferred_model_candidates",
    "preferred_model_details",
    "preferred_model_selection",
    "persistence_warning_message",
]
