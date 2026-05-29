from __future__ import annotations

import asyncio

from loushang.ai.model import Model
from loushang.coding.types import ModelSelection


class _Session:
    def __init__(self, *, current: object | None = None, selections: list[object] | None = None, details: list[object] | None = None) -> None:
        self.current = current
        self.selections = list(selections or [])
        self.details = list(details or [])
        self.set_model_calls: list[object] = []

    def get_model_selection(self) -> object | None:
        return self.current

    def get_available_models(self) -> list[object]:
        return self.selections

    def get_available_model_details(self) -> list[object]:
        return self.details

    async def set_model(self, selection: object) -> None:
        self.set_model_calls.append(selection)
        normalized = selection
        if isinstance(selection, Model):
            normalized = ModelSelection(provider=selection.provider_id, model_id=selection.id)
        self.current = normalized


def test_model_label_from_selection_hides_unknown_model() -> None:
    from loushang.coding.ui.model import model_label_from_selection

    assert model_label_from_selection(ModelSelection(provider="unknown", model_id="unknown")) is None


def test_model_label_from_selection_formats_provider_and_model() -> None:
    from loushang.coding.ui.model import model_label_from_selection

    assert model_label_from_selection(ModelSelection(provider="moonshot", model_id="kimi-for-coding")) == "moonshot/kimi-for-coding"


def test_ensure_usable_session_model_keeps_existing_usable_model() -> None:
    from loushang.coding.ui.model import ensure_usable_session_model

    current = ModelSelection(provider="moonshot", model_id="kimi-for-coding")
    session = _Session(current=current)

    result = asyncio.run(ensure_usable_session_model(session))

    assert result == current
    assert session.set_model_calls == []


def test_ensure_usable_session_model_prefers_kimi_coding_anthropic_detail() -> None:
    from loushang.coding.ui.model import ensure_usable_session_model

    preferred = Model(id="kimi-for-coding", provider="moonshot", endpoint="kimi-code-anthropic")
    fallback = Model(id="kimi-for-coding", provider="moonshot", endpoint="openai-completions:cn:coding")
    session = _Session(
        current=ModelSelection(provider="unknown", model_id="unknown"),
        details=[fallback, preferred],
    )

    result = asyncio.run(ensure_usable_session_model(session))

    assert result == ModelSelection(provider="moonshot", model_id="kimi-for-coding")
    assert session.set_model_calls == [preferred]


def test_ensure_usable_session_model_falls_back_to_available_selection() -> None:
    from loushang.coding.ui.model import ensure_usable_session_model

    fallback = ModelSelection(provider="moonshot", model_id="kimi-for-coding")
    session = _Session(
        current=ModelSelection(provider="unknown", model_id="unknown"),
        selections=[fallback],
    )

    result = asyncio.run(ensure_usable_session_model(session))

    assert result == fallback
    assert session.set_model_calls == [fallback]
