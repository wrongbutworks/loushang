from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ModelSelection:
    """Stable reference to a configured model and optional endpoint."""

    provider: str
    model_id: str
    endpoint_id: str | None = None


def normalize_model_selection(selection: object | None) -> ModelSelection | None:
    """Normalize a public model reference without resolving provider policy."""

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
    return (
        normalized is not None
        and _is_usable_value(normalized.provider)
        and _is_usable_value(normalized.model_id)
    )


def model_label_from_selection(selection: object | None) -> str | None:
    normalized = normalize_model_selection(selection)
    if normalized is None or not is_usable_model_selection(normalized):
        return None
    return f"{normalized.provider}/{normalized.model_id}"


def model_selection_ref(selection: ModelSelection) -> str:
    if selection.endpoint_id:
        return f"{selection.provider}:{selection.endpoint_id}:{selection.model_id}"
    return f"{selection.provider}/{selection.model_id}"


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
    return (
        ordered
        if not current
        else [
            *current,
            *(item for item in ordered if label_of(item) != current_label),
        ]
    )


def _string_attr(value: object, *names: str) -> str | None:
    for name in names:
        raw_value = (
            value.get(name)
            if isinstance(value, Mapping)
            else getattr(value, name, None)
        )
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
    return None


def _is_usable_value(value: str) -> bool:
    return value.strip().lower() not in {"", "unknown"}


__all__ = [
    "ModelSelection",
    "current_model_first",
    "is_usable_model_selection",
    "model_label_from_selection",
    "model_selection_ref",
    "normalize_model_selection",
]
