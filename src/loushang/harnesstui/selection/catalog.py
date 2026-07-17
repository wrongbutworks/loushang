from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from loushang.tui import (
    CommandPalette,
    CompletionItem,
    CompletionProvider,
    SearchableListItem,
    SelectItem,
)


@dataclass(frozen=True)
class ModelChoice:
    """Product-neutral model choice prepared by a product adapter."""

    label: str
    value: str
    selection: object
    endpoint_id: str = ""
    region: str = ""
    lane: str = ""
    api: str = ""
    preferred_endpoint: bool = False
    description: str = ""


def format_model_choices(
    choices: Iterable[ModelChoice],
    *,
    query: str = "",
    current_value: str | None = None,
) -> str:
    """Render a stable text listing without acquiring model data."""

    model_choices = list(choices)
    stripped_query = query.strip()
    if stripped_query:
        model_choices = filter_model_choices(model_choices, stripped_query)

    if not model_choices:
        if stripped_query:
            return f"No models match: {stripped_query}"
        return "No models available."

    lines = ["Available models:"]
    for choice in model_choices:
        is_current = choice.value == current_value
        marker = "*" if is_current else " "
        suffix = " (current)" if is_current else ""
        lines.append(f"{marker} {model_choice_display_label(choice)}{suffix}")
    return "\n".join(lines)


def model_completion_provider(
    choices: Iterable[ModelChoice],
    *,
    current_value: str | None = None,
) -> CompletionProvider:
    """Project model choices into generic TUI completion items."""

    return CompletionProvider(
        tuple(
            CompletionItem(
                value=choice.value,
                label=choice.label,
                description=model_choice_description(
                    choice,
                    current_value=current_value,
                ),
            )
            for choice in choices
        )
    )


def model_palette(
    choices: Iterable[ModelChoice],
    *,
    current_value: str | None = None,
    title: str = "Models",
) -> CommandPalette:
    """Project model choices into a generic command palette."""

    provider = model_completion_provider(choices, current_value=current_value)
    return CommandPalette.from_completion_provider(provider, title=title)


def model_search_items(
    choices: Iterable[ModelChoice],
    *,
    current_value: str | None = None,
) -> tuple[SearchableListItem, ...]:
    """Project model choices into settings/search list rows."""

    return tuple(
        SearchableListItem(
            key=choice.value,
            label=choice.label,
            value="current" if choice.value == current_value else "",
            description=choice.description,
        )
        for choice in choices
    )


def model_label_select_items(
    labels: Iterable[str],
    *,
    current_label: str | None = None,
    descriptions: Mapping[str, str] | None = None,
) -> list[SelectItem]:
    """Build numbered selector rows from product-normalized model labels."""

    model_labels = _current_model_label_first(labels, current_label=current_label)
    description_by_label = descriptions or {}
    ordinal_width = _ordinal_width(len(model_labels))
    return [
        SelectItem(
            label=f"{_ordinal(index, width=ordinal_width)} {label}",
            value=label,
            description=(
                "current"
                if label == current_label
                else description_by_label.get(label, "")
            ),
        )
        for index, label in enumerate(model_labels, start=1)
    ]


def model_choice_select_items(
    choices: Iterable[ModelChoice],
    *,
    current_value: str | None = None,
) -> list[SelectItem]:
    """Build numbered selector rows from presentation-ready model choices."""

    model_choices = list(choices)
    ordinal_width = _ordinal_width(len(model_choices))
    return [
        SelectItem(
            label=f"{_ordinal(index, width=ordinal_width)} {choice.label}",
            value=choice.value,
            description=model_choice_description(
                choice,
                current_value=current_value,
            ),
        )
        for index, choice in enumerate(model_choices, start=1)
    ]


def matching_model_choices(
    choices: Iterable[ModelChoice],
    query: str,
) -> list[ModelChoice]:
    """Match choices while preferring an exact value and then exact label."""

    model_choices = list(choices)
    needle = query.lower()
    exact_value = [choice for choice in model_choices if choice.value.lower() == needle]
    if exact_value:
        return exact_value
    labelled = [
        choice for choice in model_choices if model_choice_matches(choice, needle)
    ]
    exact_label = [choice for choice in labelled if choice.label.lower() == needle]
    return exact_label or labelled


def filter_model_choices(
    choices: Iterable[ModelChoice],
    query: str,
) -> list[ModelChoice]:
    """Return every choice whose searchable presentation matches ``query``."""

    return [choice for choice in choices if model_choice_matches(choice, query)]


def model_choice_matches(choice: ModelChoice, query: str) -> bool:
    needle = query.lower()
    return (
        needle in choice.label.lower()
        or needle in choice.value.lower()
        or bool(choice.endpoint_id and needle in choice.endpoint_id.lower())
        or bool(choice.description and needle in choice.description.lower())
    )


def model_choice_description(
    choice: ModelChoice,
    *,
    current_value: str | None = None,
) -> str:
    parts: list[str] = []
    if choice.value == current_value:
        parts.append("current")
    if choice.endpoint_id:
        parts.append(f"endpoint: {choice.endpoint_id}")
    if choice.region:
        parts.append(f"region: {choice.region}")
    if choice.lane:
        parts.append(f"lane: {choice.lane}")
    if choice.api:
        parts.append(f"protocol: {choice.api}")
    if choice.description:
        parts.append(choice.description)
    return " - ".join(parts)


def model_choice_display_label(choice: ModelChoice) -> str:
    if choice.endpoint_id:
        return f"{choice.label} (endpoint: {choice.endpoint_id})"
    return choice.label


def current_model_choice_first(
    choices: Iterable[ModelChoice],
    *,
    current_value: str | None,
) -> list[ModelChoice]:
    model_choices = list(choices)
    if current_value is None:
        return model_choices
    current = [choice for choice in model_choices if choice.value == current_value]
    if not current:
        return model_choices
    return [
        *current,
        *(choice for choice in model_choices if choice.value != current_value),
    ]


def dedupe_preferred_model_choices(
    choices: Iterable[ModelChoice],
    *,
    current_value: str | None,
) -> list[ModelChoice]:
    """Collapse duplicate labels only when a unique preferred endpoint exists."""

    model_choices = list(choices)
    by_label: dict[str, list[ModelChoice]] = {}
    for choice in model_choices:
        by_label.setdefault(choice.label, []).append(choice)

    result: list[ModelChoice] = []
    for choice in model_choices:
        group = by_label[choice.label]
        if len(group) == 1:
            result.append(choice)
            continue
        preferred = [item for item in group if item.preferred_endpoint]
        if len(preferred) != 1:
            result.append(choice)
            continue
        keep_values = {preferred[0].value}
        if current_value in {item.value for item in group}:
            keep_values.add(str(current_value))
        if choice.value in keep_values:
            result.append(choice)
    return result


def model_choice_value(
    *,
    provider: str | None,
    endpoint_id: str | None,
    model_id: str | None,
    fallback: str,
) -> str:
    if provider and endpoint_id and model_id:
        return f"{provider}:{endpoint_id}:{model_id}"
    return fallback


def _current_model_label_first(
    labels: Iterable[str],
    *,
    current_label: str | None,
) -> list[str]:
    model_labels = list(labels)
    if current_label is None:
        return model_labels
    current = [label for label in model_labels if label == current_label]
    if not current:
        return model_labels
    return [
        *current,
        *(label for label in model_labels if label != current_label),
    ]


def _ordinal_width(item_count: int) -> int:
    return max(2, len(f"{item_count}."))


def _ordinal(index: int, *, width: int) -> str:
    return f"{index}.".ljust(width)


__all__ = [
    "ModelChoice",
    "current_model_choice_first",
    "dedupe_preferred_model_choices",
    "filter_model_choices",
    "format_model_choices",
    "matching_model_choices",
    "model_choice_select_items",
    "model_choice_description",
    "model_choice_display_label",
    "model_choice_matches",
    "model_choice_value",
    "model_completion_provider",
    "model_label_select_items",
    "model_palette",
    "model_search_items",
]
