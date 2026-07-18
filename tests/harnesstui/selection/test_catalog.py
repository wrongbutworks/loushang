from __future__ import annotations

from loushang.harnesstui.selection.catalog import (
    ModelChoice,
    dedupe_preferred_model_choices,
    format_model_choices,
    matching_model_choices,
    model_choice_description,
    model_choice_display_label,
    model_choice_select_items,
    model_choice_value,
    model_completion_provider,
    model_label_select_items,
    model_search_items,
)
from loushang.harnesstui.selection.model import ModelSelectorSurface
from loushang.tui import (
    CompletionItem,
    CompletionProvider,
    InputEvent,
    InputIntent,
    SearchableListItem,
    SelectItem,
)


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


def test_model_label_select_items_preserve_current_order_ordinals_and_details() -> None:
    labels = tuple(f"provider/model-{index}" for index in range(1, 13))

    items = model_label_select_items(
        labels,
        current_label="provider/model-12",
        descriptions={
            "provider/model-12": "Current detail is intentionally hidden",
            "provider/model-1": "First model detail",
        },
    )

    assert items[0] == SelectItem(
        label="1.  provider/model-12",
        value="provider/model-12",
        description="current",
    )
    assert items[1] == SelectItem(
        label="2.  provider/model-1",
        value="provider/model-1",
        description="First model detail",
    )
    assert items[9].label == "10. provider/model-9"
    assert [item.selected_value for item in items[:2]] == [
        "provider/model-12",
        "provider/model-1",
    ]


def test_model_choice_select_items_preserve_metadata_and_description_filtering() -> (
    None
):
    choices = _choices()

    items = model_choice_select_items(
        choices,
        current_value="openai:primary:gpt-5",
    )

    assert items == [
        SelectItem(
            label="1. openai/gpt-5",
            value="openai:primary:gpt-5",
            description=(
                "current - endpoint: primary - region: us - lane: coding - "
                "protocol: responses - General coding model"
            ),
        ),
        SelectItem(
            label="2. moonshot/kimi",
            value="moonshot/kimi",
            description="Long-context model",
        ),
    ]
    assert [item.selected_value for item in items] == [
        "openai:primary:gpt-5",
        "moonshot/kimi",
    ]

    surface = ModelSelectorSurface(all_items=tuple(items))
    surface.handle_input(InputEvent(kind="text", text="REGION: US"))
    assert surface.handle_input(InputEvent(kind="key", key="enter")) == InputIntent(
        kind="select",
        text="openai:primary:gpt-5",
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
