from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from loushang.coding.types import ModelSelection


@dataclass(frozen=True)
class ModelSelectionApplyResult:
    selection: ModelSelection
    persisted: bool = False
    persistence_error: Exception | None = None


async def apply_model_selection(
    session: Any,
    selection: object,
    *,
    settings_manager: object | None = None,
    scope: str = "global",
) -> ModelSelectionApplyResult:
    normalized = normalize_model_selection(selection)
    if normalized is None:
        raise ValueError("Model selection requires provider and model id.")

    setter = getattr(session, "set_model", None)
    if not callable(setter):
        raise RuntimeError("Model selection is not available.")

    await _maybe_await(setter(normalized))

    resolved_settings_manager = (
        settings_manager
        if settings_manager is not None
        else getattr(session, "settings_manager", None)
    )
    persist = getattr(resolved_settings_manager, "set_default_model", None)
    if not callable(persist):
        return ModelSelectionApplyResult(selection=normalized)

    try:
        persist(normalized, scope=scope)
    except Exception as error:
        return ModelSelectionApplyResult(selection=normalized, persistence_error=error)
    return ModelSelectionApplyResult(selection=normalized, persisted=True)


def normalize_model_selection(selection: object | None) -> ModelSelection | None:
    if selection is None:
        return None
    provider = _string_attr(selection, "provider", "provider_id", "providerId")
    model_id = _string_attr(selection, "model_id", "modelId", "id")
    endpoint_id = _string_attr(selection, "endpoint_id", "endpoint", "endpointId")
    if provider is None or model_id is None:
        return None
    return ModelSelection(provider=provider, model_id=model_id, endpoint_id=endpoint_id)


def model_selection_ref(selection: ModelSelection) -> str:
    if selection.endpoint_id:
        return f"{selection.provider}:{selection.endpoint_id}:{selection.model_id}"
    return f"{selection.provider}/{selection.model_id}"


def persistence_warning_message(result: ModelSelectionApplyResult) -> str | None:
    if result.persistence_error is None:
        return None
    message = (
        str(result.persistence_error).strip()
        or result.persistence_error.__class__.__name__
    )
    return f"saving the default failed: {message}"


def _string_attr(value: object, *names: str) -> str | None:
    for name in names:
        if isinstance(value, Mapping):
            raw_value = value.get(name)
        else:
            raw_value = getattr(value, name, None)
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "ModelSelectionApplyResult",
    "apply_model_selection",
    "model_selection_ref",
    "normalize_model_selection",
    "persistence_warning_message",
]
