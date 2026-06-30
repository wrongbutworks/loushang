from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
from loushang.ai.contrib.openai_codex import register_openai_codex_contrib
from loushang.ai.model import Endpoint, Model
from loushang.ai.model.registry import (
    ModelRegistry,
    clear_default_model_registry,
    get_default_model_registry,
)
from loushang.ai.provider import ProviderRequest, ProviderRequestValidator


class _Provider:
    api = "custom"

    async def invoke_raw(self, request):
        del request
        yield {"type": "response_done"}


class _ValidatingProvider(_Provider):
    def __init__(self) -> None:
        self.validated_requests: list[ProviderRequest] = []

    def validate_request(self, request: ProviderRequest) -> None:
        self.validated_requests.append(request)


class _MissingApiProvider:
    async def invoke_raw(self, request):
        del request
        yield {"type": "response_done"}


class _MissingStreamRawProvider:
    api = "missing-stream"


class _NonCallableStreamRawProvider:
    api = "non-callable"
    invoke_raw = object()


class _NonCallableRequestValidatorProvider(_Provider):
    validate_request = object()


class _InvalidRequestValidatorSignatureProvider(_Provider):
    def validate_request(self) -> None:
        return None


def test_api_provider_registry_manages_raw_providers_by_source() -> None:
    registry = ApiProviderRegistry()
    provider = _Provider()
    other = _Provider()
    other.api = "other"

    registry.register_api_provider(provider, source_id="plugin-a")
    registry.register_api_provider(other, source_id="plugin-b")

    assert registry.get_api_provider("custom") is provider
    assert {item.api for item in registry.list_api_providers()} == {"custom", "other"}

    registry.unregister_api_providers("plugin-a")

    assert {item.api for item in registry.list_api_providers()} == {"other"}

    registry.clear_api_providers()

    assert registry.list_api_providers() == []


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        (_MissingApiProvider(), "api"),
        (_MissingStreamRawProvider(), "invoke_raw"),
        (_NonCallableStreamRawProvider(), "callable"),
    ],
)
def test_api_provider_registry_rejects_invalid_provider_shape(
    provider: object,
    message: str,
) -> None:
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match=message):
        registry.register_api_provider(provider)  # type: ignore[arg-type]


def test_api_provider_registry_accepts_typed_request_validator() -> None:
    registry = ApiProviderRegistry()
    provider = _ValidatingProvider()

    registry.register_api_provider(provider)

    registered = registry.get_api_provider("custom")
    assert registered is provider
    assert isinstance(registered, ProviderRequestValidator)


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        (_NonCallableRequestValidatorProvider(), "validate_request must be callable"),
        (
            _InvalidRequestValidatorSignatureProvider(),
            "validate_request must accept exactly one ProviderRequest",
        ),
    ],
)
def test_api_provider_registry_rejects_invalid_request_validator_shape(
    provider: object,
    message: str,
) -> None:
    registry = ApiProviderRegistry()

    with pytest.raises(TypeError, match=message):
        registry.register_api_provider(provider)  # type: ignore[arg-type]


def test_register_builtin_ai_providers_excludes_removed_adapters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    clear_default_model_registry()
    try:
        model_registry = get_default_model_registry()
        model_registry.register_endpoint(
            "amazon-bedrock",
            Endpoint(
                id="bedrock-converse-stream",
                provider="amazon-bedrock",
                api="bedrock-converse-stream",
                models={
                    "claude": Model(
                        id="claude",
                        provider="amazon-bedrock",
                        endpoint="bedrock-converse-stream",
                    )
                },
            ),
        )
        registry = ApiProviderRegistry()

        register_builtin_ai_providers(registry)

        apis = {provider.api for provider in registry.list_api_providers()}
        assert "azure-openai-responses" not in apis
        assert "bedrock-converse-stream" not in apis
        assert "openai-codex-responses" not in apis
    finally:
        clear_default_model_registry()


def test_azure_openai_provider_module_is_not_in_core() -> None:
    assert (
        importlib.util.find_spec("loushang.ai.providers.azure_openai_responses") is None
    )


def test_bedrock_provider_module_is_not_in_core() -> None:
    assert importlib.util.find_spec("loushang.ai.providers.bedrock_converse") is None


def test_openai_codex_contrib_registers_api_and_catalog_explicitly() -> None:
    api_registry = ApiProviderRegistry()
    model_registry = ModelRegistry()

    register_openai_codex_contrib(
        api_registry=api_registry,
        model_registry=model_registry,
    )

    apis = {provider.api for provider in api_registry.list_api_providers()}
    assert "openai-codex-responses" in apis
    assert model_registry.get_provider("openai-codex") is not None
    assert (
        model_registry.get_model(
            "openai-codex",
            "openai-codex-responses",
            "gpt-5.3-codex",
        ).id
        == "gpt-5.3-codex"
    )
