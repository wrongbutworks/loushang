from __future__ import annotations

from dataclasses import dataclass

import pytest

from loushang.ai.model import (
    Auth,
    Capabilities,
    Defaults,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    Model,
    ModelRegistry,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
    Provider,
    load_builtin_model_registry,
)
from loushang.ai.provider import (
    ResolvedRequest,
    ensure_request_api,
    resolve_endpoint_for_model,
    resolve_provider_request,
    resolve_request_for_model,
)


@dataclass
class _Options:
    api_key: str | None = "secret"
    headers: dict[str, str] | None = None
    region: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


def test_builtin_openai_style_model_resolves_adapter_config() -> None:
    registry = load_builtin_model_registry()
    model = registry.get_model("moonshot", "openai-completions", "kimi-k2.7-code")

    resolved = resolve_request_for_model(
        model,
        options=_Options(api_key="moonshot-key"),
        registry=registry,
    )

    assert resolved.provider == "moonshot"
    assert resolved.endpoint == "openai-completions"
    assert resolved.base_url == "https://api.moonshot.ai/v1"
    assert isinstance(resolved.adapter_config, OpenAICompletionsConfig)
    assert resolved.adapter_config.developer_role is False
    assert resolved.adapter_config.reasoning_format == "moonshot"
    assert resolved.upstream_model_id == "kimi-k2.7-code"


def test_resolve_provider_request_adds_default_core_adapter_config() -> None:
    model = Model(
        id="gpt-test",
        provider="custom",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://example.test/v1",
        capabilities=Capabilities(reasoning=True, stream=True),
        auth=Auth(api_key_env="TEST_API_KEY"),
    )

    resolved = resolve_provider_request(
        "openai-responses",
        model,
        options=_Options(api_key="token"),
    )

    assert isinstance(resolved.adapter_config, OpenAIResponsesConfig)
    assert resolved.adapter_config.prompt_cache_key is True


def test_resolve_provider_request_rejects_wrong_adapter_config_type() -> None:
    model = Model(id="m", provider="custom", endpoint="openai-responses")
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-responses",
        api="openai-responses",
        base_url="https://example.test/v1",
        adapter_config=OpenAICompletionsConfig(),
    )

    with pytest.raises(TypeError, match="OpenAIResponsesConfig"):
        resolve_provider_request("openai-responses", model, request=request)


def test_ensure_request_api_rejects_mismatch() -> None:
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://example.test/v1",
    )

    with pytest.raises(ValueError, match="Mismatched api"):
        ensure_request_api("openai-responses", request)


def test_resolve_provider_request_uses_runtime_adapter_resolver() -> None:
    model = Model(id="m", provider="custom", endpoint="custom-api", api="custom-api")
    request = ResolvedRequest(
        provider="custom",
        endpoint="custom-api",
        api="custom-api",
        base_url="https://example.test/v1",
        adapter_config={"raw": True},
    )

    resolved = resolve_provider_request(
        "custom-api",
        model,
        request=request,
        adapter_config_resolver=lambda current: {"resolved": current},
    )

    assert resolved.adapter_config == {"resolved": {"raw": True}}


def test_resolve_provider_request_keeps_runtime_config_when_resolver_matches() -> None:
    model = Model(id="m", provider="custom", endpoint="custom-api", api="custom-api")
    config = {"raw": True}
    request = ResolvedRequest(
        provider="custom",
        endpoint="custom-api",
        api="custom-api",
        base_url="https://example.test/v1",
        adapter_config=config,
    )

    resolved = resolve_provider_request(
        "custom-api",
        model,
        request=request,
        adapter_config_resolver=lambda current: current,
    )

    assert resolved is request


def test_model_overrides_defaults_and_capabilities() -> None:
    endpoint_model = Model(
        id="m",
        provider="custom",
        endpoint="openai-completions",
        defaults=Defaults({"maxOutputTokens": 1000}),
        capabilities=Capabilities(reasoning=True, stream=True, max_tokens=4000),
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://example.test/v1",
        auth=Auth(api_key_env="TEST_API_KEY"),
        adapter=OpenAICompletionsConfig(developer_role=False),
        models={"m": endpoint_model},
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    caller_model = Model(
        id="m",
        provider="custom",
        endpoint="openai-completions",
        defaults=Defaults({"maxOutputTokens": 2000}),
        capabilities=Capabilities(reasoning=False, stream=True, max_tokens=8000),
    )

    resolved = resolve_request_for_model(
        caller_model,
        options=_Options(api_key="token"),
        registry=registry,
    )

    assert resolved.max_tokens == 2000
    assert resolved.capabilities.max_tokens == 8000
    assert isinstance(resolved.adapter_config, OpenAICompletionsConfig)
    assert resolved.adapter_config.developer_role is False


def test_ad_hoc_model_adapter_merges_with_registered_endpoint_adapter() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://example.test/v1",
        auth=Auth(api_key_env="TEST_API_KEY"),
        adapter=OpenAICompletionsConfig(
            developer_role=False,
            max_output_tokens_field="max_tokens",
        ),
        models={},
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    caller_model = Model(
        id="ad-hoc",
        provider="custom",
        endpoint="openai-completions",
        adapter=OpenAICompletionsConfig(reasoning_format="moonshot"),
    )

    resolved = resolve_request_for_model(
        caller_model,
        options=_Options(api_key="token"),
        registry=registry,
    )

    assert isinstance(resolved.adapter_config, OpenAICompletionsConfig)
    assert resolved.adapter_config.developer_role is False
    assert resolved.adapter_config.max_output_tokens_field == "max_tokens"
    assert resolved.adapter_config.reasoning_format == "moonshot"


def test_bound_model_endpoint_snapshot_preserves_adapter_transport_and_routing() -> (
    None
):
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://example.test/v1",
        auth=Auth(api_key_env="TEST_API_KEY"),
        adapter=OpenAICompletionsConfig(reasoning_format="moonshot"),
        transport=EndpointTransport(kind="httpx", timeout=10),
        routing=EndpointRouting.from_raw(
            {"requestOverrides": {"openrouter": {"order": ["x"]}}}
        ),
    )
    bound = endpoint.bind_model(
        Model(
            id="m",
            provider="custom",
            endpoint="openai-completions",
            capabilities=Capabilities(stream=True),
        )
    )

    resolved_endpoint = resolve_endpoint_for_model(bound, registry=ModelRegistry())
    resolved = resolve_request_for_model(
        bound,
        options=_Options(api_key="token"),
        registry=ModelRegistry(),
    )

    assert resolved_endpoint.base_url == "https://example.test/v1"
    assert isinstance(resolved.adapter_config, OpenAICompletionsConfig)
    assert resolved.adapter_config.reasoning_format == "moonshot"
    assert resolved.transport.kind == "httpx"
    assert resolved.transport.timeout == 10
    assert resolved.routing.request_overrides == {"openrouter": {"order": ["x"]}}


def test_resolve_request_switches_endpoint_by_selected_region() -> None:
    endpoint_us = Endpoint(
        id="regional-us",
        provider="custom",
        api="openai-completions",
        base_url="https://us.example.test/v1",
        region="us",
        auth=Auth(api_key_env="TEST_API_KEY"),
        adapter=OpenAICompletionsConfig(reasoning_format="openai"),
        models={
            "m": Model(
                id="m",
                provider="custom",
                endpoint="regional-us",
                defaults=Defaults({"maxOutputTokens": 100}),
            )
        },
    )
    endpoint_eu = Endpoint(
        id="regional-eu",
        provider="custom",
        api="openai-completions",
        base_url="https://eu.example.test/v1",
        region="eu",
        auth=Auth(api_key_env="TEST_API_KEY"),
        adapter=OpenAICompletionsConfig(reasoning_format="openai"),
        models={
            "m": Model(
                id="m",
                provider="custom",
                endpoint="regional-eu",
                defaults=Defaults({"maxOutputTokens": 200}),
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "custom": Provider(
                id="custom",
                endpoints={endpoint_us.id: endpoint_us, endpoint_eu.id: endpoint_eu},
            )
        }
    )
    caller_model = Model(
        id="m",
        provider="custom",
        endpoint="regional-us",
        adapter=OpenAICompletionsConfig(reasoning_format="caller"),
        defaults=Defaults({"maxOutputTokens": 300}),
        capabilities=Capabilities(max_tokens=300, stream=True),
    )

    resolved = resolve_request_for_model(
        caller_model,
        options=_Options(api_key="token", region="eu"),
        registry=registry,
    )

    assert resolved.endpoint == "regional-eu"
    assert resolved.base_url == "https://eu.example.test/v1"
    assert resolved.region == "eu"
    assert resolved.max_tokens == 300
    assert resolved.capabilities.max_tokens == 300
    assert isinstance(resolved.adapter_config, OpenAICompletionsConfig)
    assert resolved.adapter_config.reasoning_format == "caller"


def test_base_url_env_template_is_expanded() -> None:
    model = Model(
        id="m",
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://{HOST}/v1",
        auth=Auth(api_key_env="TEST_API_KEY"),
    )

    resolved = resolve_request_for_model(
        model,
        options=_Options(api_key="token"),
        registry=ModelRegistry(),
        env={"HOST": "example.test"},
    )

    assert resolved.base_url == "https://example.test/v1"


def test_missing_base_url_env_template_fails() -> None:
    model = Model(
        id="m",
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://{HOST}/v1",
        auth=Auth(api_key_env="TEST_API_KEY"),
    )

    with pytest.raises(ValueError, match="Environment variable HOST"):
        resolve_request_for_model(
            model,
            options=_Options(api_key="token"),
            registry=ModelRegistry(),
            env={},
        )
