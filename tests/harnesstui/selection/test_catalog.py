from __future__ import annotations

from loushang.harnesstui.selection.catalog import (
    ModelChoice,
    dedupe_preferred_model_choices,
    format_model_choices,
    matching_model_choices,
    model_choice_description,
    model_choice_display_label,
    model_choice_value,
    model_completion_provider,
    model_search_items,
)
from loushang.tui import CompletionItem, CompletionProvider, SearchableListItem


def _choices() -> tuple[ModelChoice, ...]:
    return (
        ModelChoice(
            label="openai/gpt-5",
            value="openai:primary:gpt-5",
            selection=object(),
            endpoint_id="primary",
            region="us",
            lane="coding",
            api="responses",
            description="General coding model",
        ),
        ModelChoice(
            label="moonshot/kimi",
            value="moonshot/kimi",
            selection=object(),
            description="Long-context model",
        ),
    )


def test_model_choice_text_and_completion_projection() -> None:
    choices = _choices()

    assert format_model_choices(
        choices,
        current_value="openai:primary:gpt-5",
    ) == (
        "Available models:\n"
        "* openai/gpt-5 (endpoint: primary) (current)\n"
        "  moonshot/kimi"
    )
    assert model_completion_provider(
        choices,
        current_value="openai:primary:gpt-5",
    ) == CompletionProvider(
        (
            CompletionItem(
                value="openai:primary:gpt-5",
                label="openai/gpt-5",
                description=(
                    "current - endpoint: primary - region: us - lane: coding - "
                    "protocol: responses - General coding model"
                ),
            ),
            CompletionItem(
                value="moonshot/kimi",
                label="moonshot/kimi",
                description="Long-context model",
            ),
        )
    )


def test_model_choice_filtering_and_exact_match_priority() -> None:
    choices = _choices()

    assert format_model_choices(choices, query="LONG-CONTEXT") == (
        "Available models:\n  moonshot/kimi"
    )
    assert matching_model_choices(choices, "openai:primary:gpt-5") == [choices[0]]
    assert matching_model_choices(choices, "moonshot/kimi") == [choices[1]]
    assert format_model_choices(choices, query="missing") == "No models match: missing"


def test_model_choice_metadata_helpers_and_settings_rows() -> None:
    choice = _choices()[0]

    assert model_choice_display_label(choice) == "openai/gpt-5 (endpoint: primary)"
    assert model_choice_description(
        choice,
        current_value=choice.value,
    ).startswith("current - endpoint: primary")
    assert (
        model_choice_value(
            provider="openai",
            endpoint_id="primary",
            model_id="gpt-5",
            fallback="openai/gpt-5",
        )
        == "openai:primary:gpt-5"
    )
    assert model_search_items(_choices(), current_value=choice.value) == (
        SearchableListItem(
            key="openai:primary:gpt-5",
            label="openai/gpt-5",
            value="current",
            description="General coding model",
        ),
        SearchableListItem(
            key="moonshot/kimi",
            label="moonshot/kimi",
            description="Long-context model",
        ),
    )


def test_preferred_endpoint_dedupe_preserves_current_nonpreferred_choice() -> None:
    preferred = ModelChoice(
        label="provider/model",
        value="provider:preferred:model",
        selection=object(),
        preferred_endpoint=True,
    )
    current = ModelChoice(
        label="provider/model",
        value="provider:current:model",
        selection=object(),
    )
    other = ModelChoice(
        label="other/model",
        value="other/model",
        selection=object(),
    )

    assert dedupe_preferred_model_choices(
        (preferred, current, other),
        current_value=current.value,
    ) == [preferred, current, other]
    assert dedupe_preferred_model_choices(
        (preferred, current, other),
        current_value=None,
    ) == [preferred, other]
