from __future__ import annotations

import asyncio
from types import SimpleNamespace

from loushang.coding.types import ModelSelection


class _Session:
    def __init__(self) -> None:
        self.set_model_calls: list[ModelSelection] = []
        self.selection = ModelSelection(provider="moonshot", model_id="kimi-for-coding")

    def get_model_selection(self) -> ModelSelection:
        return self.selection

    def get_available_models(self) -> list[object]:
        return [
            ModelSelection(provider="moonshot", model_id="kimi-for-coding"),
            SimpleNamespace(provider_id="openai", id="gpt-5.4"),
        ]

    async def set_model(self, selection: ModelSelection) -> None:
        self.set_model_calls.append(selection)
        self.selection = selection


class _CurrentSecondSession(_Session):
    def __init__(self) -> None:
        super().__init__()
        self.selection = ModelSelection(provider="openai", model_id="gpt-5.4")


class _AmbiguousSession(_Session):
    def get_available_models(self) -> list[object]:
        return [
            ModelSelection(provider="moonshot", model_id="kimi-for-coding"),
            ModelSelection(provider="moonshot", model_id="kimi-latest"),
            ModelSelection(provider="openai", model_id="gpt-5.4"),
        ]


class _SessionWithModelDetails(_Session):
    def get_available_model_details(self) -> list[object]:
        return [
            SimpleNamespace(
                provider_id="openai",
                id="gpt-5.4",
                name="Strong model for everyday coding.",
            )
        ]


class _DuplicateEndpointSession(_Session):
    def __init__(self) -> None:
        super().__init__()
        self.model_details = [
            SimpleNamespace(
                provider_id="dashscope",
                endpoint_id="openai-responses",
                id="qwen3.6-plus",
                api="openai-responses",
                region="cn",
                preferred_endpoint=True,
                name="Qwen 3.6 Plus",
            ),
            SimpleNamespace(
                provider_id="dashscope",
                endpoint_id="openai-completions:cn",
                id="qwen3.6-plus",
                api="openai-completions",
                region="cn",
                lane="coding",
                name="Qwen 3.6 Plus",
            ),
        ]

    def get_available_models(self) -> list[object]:
        return [
            ModelSelection(provider="dashscope", model_id="qwen3.6-plus"),
            ModelSelection(provider="dashscope", model_id="qwen3.6-plus"),
        ]

    def get_available_model_details(self) -> list[object]:
        return self.model_details


class _DuplicateEndpointCurrentSession(_DuplicateEndpointSession):
    def __init__(self) -> None:
        super().__init__()
        self.selection = self.model_details[1]


class _DuplicateEndpointAgentModelSession(_DuplicateEndpointSession):
    def __init__(self) -> None:
        super().__init__()
        self.selection = ModelSelection(provider="dashscope", model_id="qwen3.6-plus")
        self.agent = SimpleNamespace(model=self.model_details[1])


class _AmbiguousDuplicateEndpointSession(_DuplicateEndpointSession):
    def __init__(self) -> None:
        super().__init__()
        for detail in self.model_details:
            detail.preferred_endpoint = False


def test_format_available_models_marks_current_model() -> None:
    from loushang.coding.ui.model_list import format_available_models

    text = asyncio.run(format_available_models(_Session()))

    assert text == (
        "Available models:\n"
        "* moonshot/kimi-for-coding (current)\n"
        "  openai/gpt-5.4"
    )


def test_format_available_models_filters_by_query() -> None:
    from loushang.coding.ui.model_list import format_available_models

    text = asyncio.run(format_available_models(_Session(), query="gpt"))

    assert text == "Available models:\n  openai/gpt-5.4"


def test_format_available_models_lists_current_model_first() -> None:
    from loushang.coding.ui.model_list import format_available_models

    text = asyncio.run(format_available_models(_CurrentSecondSession()))

    assert text == (
        "Available models:\n"
        "* openai/gpt-5.4 (current)\n"
        "  moonshot/kimi-for-coding"
    )


def test_format_available_models_reports_empty_matches() -> None:
    from loushang.coding.ui.model_list import format_available_models

    text = asyncio.run(format_available_models(_Session(), query="missing"))

    assert text == "No models match: missing"


def test_available_model_completion_provider_exposes_structured_items() -> None:
    from loushang.coding.ui.model_list import available_model_completion_provider
    from loushang.tui import CompletionItem, CompletionProvider

    provider = asyncio.run(available_model_completion_provider(_Session()))

    assert provider == CompletionProvider(
        (
            CompletionItem(
                value="moonshot/kimi-for-coding",
                label="moonshot/kimi-for-coding",
                description="current",
            ),
            CompletionItem(value="openai/gpt-5.4", label="openai/gpt-5.4"),
        )
    )


def test_available_model_completion_provider_uses_model_detail_descriptions() -> None:
    from loushang.coding.ui.model_list import available_model_completion_provider
    from loushang.tui import CompletionItem, CompletionProvider

    provider = asyncio.run(available_model_completion_provider(_SessionWithModelDetails()))

    assert provider == CompletionProvider(
        (
            CompletionItem(
                value="moonshot/kimi-for-coding",
                label="moonshot/kimi-for-coding",
                description="current",
            ),
            CompletionItem(
                value="openai/gpt-5.4",
                label="openai/gpt-5.4",
                description="Strong model for everyday coding.",
            ),
        )
    )


def test_available_model_completion_provider_lists_current_model_first() -> None:
    from loushang.coding.ui.model_list import available_model_completion_provider

    provider = asyncio.run(available_model_completion_provider(_CurrentSecondSession()))

    assert [item.value for item in provider.items] == [
        "openai/gpt-5.4",
        "moonshot/kimi-for-coding",
    ]
    assert provider.items[0].description == "current"


def test_available_model_palette_reuses_structured_model_items() -> None:
    from loushang.coding.ui.model_list import available_model_palette
    from loushang.tui import CommandPalette, CommandPaletteItem

    palette = asyncio.run(available_model_palette(_Session(), title="Models"))

    assert palette == CommandPalette(
        items=(
            CommandPaletteItem(
                value="moonshot/kimi-for-coding",
                label="moonshot/kimi-for-coding",
                description="current",
            ),
            CommandPaletteItem(value="openai/gpt-5.4", label="openai/gpt-5.4"),
        ),
        title="Models",
    )


def test_select_available_model_sets_unique_match() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _Session()
    text = asyncio.run(select_available_model(session, query="gpt"))

    assert text == "Model set: openai/gpt-5.4"
    assert session.set_model_calls == [ModelSelection(provider="openai", model_id="gpt-5.4")]


def test_select_available_model_lists_models_when_query_is_empty() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _Session()
    text = asyncio.run(select_available_model(session, query=""))

    assert text == (
        "Available models:\n"
        "* moonshot/kimi-for-coding (current)\n"
        "  openai/gpt-5.4"
    )
    assert session.set_model_calls == []


def test_select_available_model_uses_injected_palette_chooser() -> None:
    from loushang.coding.ui.model_list import select_available_model
    from loushang.tui import CommandPalette

    session = _Session()
    seen: list[CommandPalette] = []

    async def choose(palette: CommandPalette) -> str:
        seen.append(palette)
        return "openai/gpt-5.4"

    text = asyncio.run(select_available_model(session, query="", choose=choose))

    assert text == "Model set: openai/gpt-5.4"
    assert session.set_model_calls == [ModelSelection(provider="openai", model_id="gpt-5.4")]
    assert seen
    assert [item.value for item in seen[0].items] == [
        "moonshot/kimi-for-coding",
        "openai/gpt-5.4",
    ]


def test_select_available_model_reports_cancelled_palette_choice() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _Session()

    text = asyncio.run(select_available_model(session, query="", choose=lambda _palette: None))

    assert text == "Model selection cancelled."
    assert session.set_model_calls == []


def test_select_available_model_reports_ambiguous_matches_with_hint() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _AmbiguousSession()
    text = asyncio.run(select_available_model(session, query="moonshot"))

    assert text == (
        "Multiple models match:\n"
        "  moonshot/kimi-for-coding\n"
        "  moonshot/kimi-latest\n"
        "Use /model <full model> to select one."
    )
    assert session.set_model_calls == []


def test_select_available_model_uses_full_identity_for_duplicate_endpoint_choice() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _DuplicateEndpointSession()
    text = asyncio.run(select_available_model(session, query="dashscope:openai-responses:qwen3.6-plus"))

    assert text == "Model set: dashscope/qwen3.6-plus (endpoint: openai-responses)"
    assert session.set_model_calls == [session.model_details[0]]


def test_select_available_model_uses_preferred_endpoint_for_duplicate_label() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _DuplicateEndpointSession()
    text = asyncio.run(select_available_model(session, query="dashscope/qwen3.6-plus"))

    assert text == "Model set: dashscope/qwen3.6-plus (endpoint: openai-responses)"
    assert session.set_model_calls == [session.model_details[0]]


def test_select_available_model_reports_duplicate_endpoint_label_as_ambiguous_without_preferred() -> None:
    from loushang.coding.ui.model_list import select_available_model

    session = _AmbiguousDuplicateEndpointSession()
    text = asyncio.run(select_available_model(session, query="dashscope/qwen3.6-plus"))

    assert text == (
        "Multiple models match:\n"
        "  dashscope/qwen3.6-plus (endpoint: openai-responses)\n"
        "  dashscope/qwen3.6-plus (endpoint: openai-completions:cn)\n"
        "Use /model <provider:endpoint:model> or choose one from the model list."
    )
    assert session.set_model_calls == []


def test_available_model_completion_provider_marks_only_current_endpoint() -> None:
    from loushang.coding.ui.model_list import available_model_completion_provider

    provider = asyncio.run(available_model_completion_provider(_DuplicateEndpointCurrentSession()))

    assert [item.value for item in provider.items] == [
        "dashscope:openai-completions:cn:qwen3.6-plus",
        "dashscope:openai-responses:qwen3.6-plus",
    ]
    assert (
        provider.items[0].description
        == "current - endpoint: openai-completions:cn - region: cn - lane: coding - protocol: openai-completions - Qwen 3.6 Plus"
    )
    assert (
        provider.items[1].description
        == "endpoint: openai-responses - region: cn - protocol: openai-responses - Qwen 3.6 Plus"
    )


def test_available_model_completion_provider_uses_agent_model_endpoint_for_current() -> None:
    from loushang.coding.ui.model_list import available_model_completion_provider

    provider = asyncio.run(available_model_completion_provider(_DuplicateEndpointAgentModelSession()))

    assert [item.value for item in provider.items] == [
        "dashscope:openai-completions:cn:qwen3.6-plus",
        "dashscope:openai-responses:qwen3.6-plus",
    ]
    assert (
        provider.items[0].description
        == "current - endpoint: openai-completions:cn - region: cn - lane: coding - protocol: openai-completions - Qwen 3.6 Plus"
    )
    assert (
        provider.items[1].description
        == "endpoint: openai-responses - region: cn - protocol: openai-responses - Qwen 3.6 Plus"
    )


def test_available_model_completion_provider_dedupes_to_preferred_endpoint() -> None:
    from loushang.coding.ui.model_list import available_model_completion_provider

    provider = asyncio.run(available_model_completion_provider(_DuplicateEndpointSession()))

    assert [item.value for item in provider.items] == [
        "dashscope:openai-responses:qwen3.6-plus",
    ]
    assert (
        provider.items[0].description
        == "endpoint: openai-responses - region: cn - protocol: openai-responses - Qwen 3.6 Plus"
    )
