from __future__ import annotations

import pytest

from loushang.ai.model import Capabilities, Endpoint, Model, Provider
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.coding.control.model_registry import ModelRegistry
from loushang.coding.types import ModelSelection


def _model(model_id: str, *, endpoint: str) -> Model:
    return Model(
        id=model_id,
        provider="provider",
        endpoint=endpoint,
        capabilities=Capabilities(input=("text",), output=("text",)),
    )


def _registry(*, primary_preferred: bool = True) -> ModelRegistry:
    primary = Endpoint(
        id="primary",
        provider="provider",
        api="openai-responses",
        preferred=primary_preferred,
        models={"chat": _model("chat", endpoint="primary")},
    )
    secondary = Endpoint(
        id="secondary",
        provider="provider",
        api="openai-completions",
        models={"chat": _model("chat", endpoint="secondary")},
    )
    ai_registry = AiModelRegistry.from_providers(
        {
            "provider": Provider(
                id="provider",
                endpoints={primary.id: primary, secondary.id: secondary},
            )
        }
    )
    return ModelRegistry(ai_registry)


def test_control_model_registry_resolves_provider_model_to_preferred_endpoint() -> None:
    model = _registry().build_model(ModelSelection(provider="provider", model_id="chat"))

    assert model.endpoint_id == "primary"


def test_control_model_registry_resolves_explicit_endpoint_selection() -> None:
    model = _registry().build_model(
        ModelSelection(provider="provider", endpoint_id="secondary", model_id="chat")
    )

    assert model.endpoint_id == "secondary"


def test_control_model_registry_ambiguity_error_lists_explicit_alternatives() -> None:
    with pytest.raises(ValueError) as exc_info:
        _registry(primary_preferred=False).build_model(
            ModelSelection(provider="provider", model_id="chat")
        )

    message = str(exc_info.value)
    assert "provider:primary:chat" in message
    assert "provider:secondary:chat" in message
