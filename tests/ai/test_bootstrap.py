from __future__ import annotations

import importlib.util

import pytest

from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.bootstrap import register_builtin_ai_providers
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


def test_register_builtin_ai_providers_registers_only_core_protocol_adapters() -> None:
    registry = ApiProviderRegistry()

    register_builtin_ai_providers(registry)

    assert {provider.api for provider in registry.list_api_providers()} == {
        "anthropic-messages",
        "openai-completions",
        "openai-responses",
    }


def test_azure_openai_provider_module_is_not_in_core() -> None:
    assert (
        importlib.util.find_spec("loushang.ai.protocols.azure_openai_responses") is None
    )


def test_bedrock_provider_module_is_not_in_core() -> None:
    assert importlib.util.find_spec("loushang.ai.protocols.bedrock_converse") is None
