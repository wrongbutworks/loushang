from __future__ import annotations

from dataclasses import dataclass

import pytest

from loushang.ai.model import (
    AnthropicMessagesConfig,
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
    default_adapter_config,
    load_builtin_model_registry,
)
from loushang.ai.provider import (
    ProviderRequest,
    ensure_request_api,
    normalize_provider_request_for_api,
    resolve_endpoint_for_model,
    resolve_request_for_model,
)


@dataclass
class _Options:
    api_key: str | None = "secret"
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


def _model(
    *,
    api: str = "openai-responses",
    endpoint: str | None = None,
    adapter: object | None = None,
    region: str | None = None,
    base_url: str | None = "https://example.test/v1",
    capabilities: Capabilities | None = None,
    defaults: Defaults | None = None,
    transport: EndpointTransport | None = None,
    routing: EndpointRouting | None = None,
    upstream_id: str | None = None,
    auth: Auth | None = None,
) -> Model:
    return Model(
        id="model-a",
        provider="custom",
        endpoint=endpoint or api,
        api=api,
        base_url=base_url,
        region=region,
        auth=auth,
        capabilities=capabilities or Capabilities(stream=True),
        adapter=adapter,  # type: ignore[arg-type]
        defaults=defaults or Defaults(),
        transport=transport or EndpointTransport(),
        routing=routing or EndpointRouting(),
        upstream_id=upstream_id,
    )


def _request(model: Model, **overrides: object) -> ProviderRequest:
    values: dict[str, object] = {
        "model": model,
        "provider": model.provider_id,
        "endpoint": model.endpoint_id,
        "api": model.api,
        "base_url": model.base_url,
        "region": model.region,
        "capabilities": model.capabilities,
        "adapter_config": model.adapter or default_adapter_config(model.api or ""),
        "defaults": dict(model.defaults),
        "transport": model.transport,
        "routing": model.routing,
        "upstream_model_id": model.upstream_id or model.id,
    }
    values.update(overrides)
    return ProviderRequest(**values)  # type: ignore[arg-type]


def test_builtin_openai_style_model_resolves_its_bound_facts() -> None:
    model = load_builtin_model_registry().get_model(
        "moonshot", "openai-completions", "kimi-k2.7-code"
    )

    resolved = resolve_request_for_model(
        model,
        options=_Options(api_key="moonshot-key"),
    )

    assert resolved.model is model
    assert resolved.provider == "moonshot"
    assert resolved.endpoint == "openai-completions"
    assert resolved.base_url == "https://api.moonshot.cn/v1"
    assert isinstance(resolved.adapter_config, OpenAICompletionsConfig)
    assert resolved.adapter_config.reasoning_format == "moonshot"
    assert resolved.upstream_model_id == "kimi-k2.7-code"


def test_resolver_accepts_concrete_model_without_incidental_endpoint_metadata() -> None:
    model = Model(
        id="faux-model",
        provider="faux-provider",
        endpoint="faux-api",
        api="faux-api",
    )

    resolved = resolve_request_for_model(
        model,
        options=_Options(api_key="token"),
        env={"LOUSHANG_REGION": "ignored"},
    )

    assert resolved.model is model
    assert resolved.provider == "faux-provider"
    assert resolved.endpoint == "faux-api"
    assert resolved.api == "faux-api"
    assert resolved.region is None


@pytest.mark.parametrize(
    "model",
    [
        Model(id="missing-all"),
        Model(id="missing-api", provider="custom", endpoint="responses"),
        Model(id="missing-provider", api="openai-responses"),
    ],
)
def test_resolver_rejects_unbound_model(model: Model) -> None:
    with pytest.raises(ValueError, match="not bound to a concrete provider endpoint"):
        resolve_request_for_model(model, options=_Options(api_key="token"))


def test_resolver_rejects_non_model_input() -> None:
    with pytest.raises(TypeError, match="model must be Model"):
        resolve_request_for_model(object())  # type: ignore[arg-type]


def test_resolver_uses_bound_model_without_registry_reselection() -> None:
    us_capabilities = Capabilities(stream=True)
    eu_capabilities = Capabilities(reasoning=True)
    us_defaults = Defaults.from_raw({"temperature": 0.1})
    eu_defaults = Defaults.from_raw({"temperature": 0.7})
    us_adapter = OpenAICompletionsConfig(reasoning_format="moonshot")
    eu_adapter = OpenAICompletionsConfig(reasoning_format="openai")
    endpoint_us = Endpoint(
        id="regional-us",
        provider="custom",
        api="openai-completions",
        base_url="https://us.example.test/v1",
        region="us",
        auth=Auth(
            header="x-region-key",
            prefix="",
            extra_headers={"x-selected-region": "us"},
        ),
        adapter=us_adapter,
        defaults=us_defaults,
        models={
            "m": Model(
                id="m",
                provider="custom",
                endpoint="regional-us",
                capabilities=us_capabilities,
                upstream_id="upstream-us",
            )
        },
    )
    endpoint_eu = Endpoint(
        id="regional-eu",
        provider="custom",
        api="openai-completions",
        base_url="https://eu.example.test/v1",
        region="eu",
        auth=Auth(
            header="x-region-key",
            prefix="",
            extra_headers={"x-selected-region": "eu"},
        ),
        adapter=eu_adapter,
        defaults=eu_defaults,
        models={
            "m": Model(
                id="m",
                provider="custom",
                endpoint="regional-eu",
                capabilities=eu_capabilities,
                upstream_id="upstream-eu",
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
    selected_us = registry.get_model("custom", "regional-us", "m")

    resolved_us = resolve_request_for_model(
        selected_us,
        options=_Options(api_key="token"),
        env={"LOUSHANG_REGION": "eu"},
    )

    assert resolved_us.model is selected_us
    assert resolved_us.provider == "custom"
    assert resolved_us.endpoint == "regional-us"
    assert resolved_us.api == "openai-completions"
    assert resolved_us.base_url == "https://us.example.test/v1"
    assert resolved_us.region == "us"
    assert resolved_us.capabilities == us_capabilities
    assert resolved_us.defaults == dict(us_defaults)
    assert resolved_us.adapter_config == us_adapter
    assert resolved_us.upstream_model_id == "upstream-us"
    assert resolved_us.headers == {
        "x-region-key": "token",
        "x-selected-region": "us",
    }

    selected_eu = registry.get_model("custom", "regional-eu", "m")
    resolved_eu = resolve_request_for_model(
        selected_eu,
        options=_Options(api_key="token"),
        env={"LOUSHANG_REGION": "us"},
    )

    assert resolved_eu.model is selected_eu
    assert resolved_eu.endpoint == "regional-eu"
    assert resolved_eu.base_url == "https://eu.example.test/v1"
    assert resolved_eu.region == "eu"
    assert resolved_eu.capabilities == eu_capabilities
    assert resolved_eu.defaults == dict(eu_defaults)
    assert resolved_eu.adapter_config == eu_adapter
    assert resolved_eu.upstream_model_id == "upstream-eu"
    assert resolved_eu.headers == {
        "x-region-key": "token",
        "x-selected-region": "eu",
    }


def test_bound_model_endpoint_snapshot_preserves_model_facts() -> None:
    model = _model(
        api="openai-completions",
        adapter=OpenAICompletionsConfig(reasoning_format="moonshot"),
        transport=EndpointTransport(kind="httpx", timeout=10),
        routing=EndpointRouting.from_raw(
            {"requestOverrides": {"openrouter": {"order": ["x"]}}}
        ),
    )

    endpoint = resolve_endpoint_for_model(model)

    assert endpoint is not None
    assert endpoint.base_url == model.base_url
    assert endpoint.adapter == model.adapter
    assert endpoint.transport == model.transport
    assert endpoint.routing == model.routing
    assert endpoint.get_model(model.id) is model


def test_base_url_env_template_is_expanded_from_bound_model() -> None:
    model = _model(base_url="https://{HOST}/v1")

    resolved = resolve_request_for_model(
        model,
        options=_Options(api_key="token"),
        env={"HOST": "example.test"},
    )

    assert resolved.base_url == "https://example.test/v1"


def test_missing_base_url_env_template_fails() -> None:
    model = _model(base_url="https://{HOST}/v1")

    with pytest.raises(ValueError, match="Environment variable HOST"):
        resolve_request_for_model(model, options=_Options(api_key="token"), env={})


def test_provider_request_rejects_unrelated_base_url() -> None:
    model = _model(base_url="https://catalog.example/v1")

    with pytest.raises(ValueError, match="base_url"):
        _request(
            model,
            base_url="https://runtime.example/v1",
            headers={"Authorization": "Bearer token"},
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("provider", "other"),
        ("endpoint", "other"),
        ("api", "openai-completions"),
        ("region", "other"),
        ("capabilities", Capabilities(reasoning=True)),
        ("defaults", {"temperature": 0.5}),
        ("transport", EndpointTransport(kind="httpx")),
        (
            "routing",
            EndpointRouting.from_raw({"requestOverrides": {"x": {"value": 1}}}),
        ),
        ("upstream_model_id", "other"),
        ("adapter_config", OpenAICompletionsConfig()),
    ],
)
def test_provider_request_rejects_facts_mismatched_with_model(
    field_name: str,
    value: object,
) -> None:
    model = _model(region="global")

    with pytest.raises(ValueError, match=field_name):
        _request(model, **{field_name: value})


def test_provider_request_requires_typed_model() -> None:
    assert "candidate_base_urls" not in ProviderRequest.__dataclass_fields__
    with pytest.raises(TypeError, match="model must be Model"):
        ProviderRequest(
            model=object(),  # type: ignore[arg-type]
            provider="custom",
            endpoint="openai-responses",
            api="openai-responses",
            base_url=None,
        )


def test_provider_request_repr_redacts_headers() -> None:
    request = _request(
        _model(),
        headers={
            "Authorization": "Bearer access-secret",
            "chatgpt-account-id": "account-secret",
        },
    )

    rendered = repr(request)

    assert "access-secret" not in rendered
    assert "account-secret" not in rendered


def test_normalize_provider_request_adds_model_default_core_adapter_config() -> None:
    model = _model(adapter=None)
    request = ProviderRequest(
        model=model,
        provider=model.provider_id,
        endpoint=model.endpoint_id,
        api=model.api or "",
        base_url=model.base_url,
        capabilities=model.capabilities,
        defaults=dict(model.defaults),
        transport=model.transport,
        routing=model.routing,
    )

    assert isinstance(request.adapter_config, OpenAIResponsesConfig)
    assert normalize_provider_request_for_api("openai-responses", request) == request


@pytest.mark.parametrize(
    ("api", "adapter_config", "expected_type"),
    [
        ("openai-completions", AnthropicMessagesConfig(), "OpenAICompletionsConfig"),
        ("openai-responses", OpenAICompletionsConfig(), "OpenAIResponsesConfig"),
        ("anthropic-messages", OpenAICompletionsConfig(), "AnthropicMessagesConfig"),
    ],
)
def test_normalize_provider_request_rejects_wrong_core_adapter_config_type(
    api: str,
    adapter_config: object,
    expected_type: str,
) -> None:
    model = _model(api=api, adapter=adapter_config)
    request = _request(model)

    with pytest.raises(TypeError, match=expected_type):
        normalize_provider_request_for_api(api, request)


def test_ensure_request_api_rejects_mismatch() -> None:
    request = _request(_model(api="openai-completions"))

    with pytest.raises(ValueError, match="Mismatched api"):
        ensure_request_api("openai-responses", request)


def test_normalize_provider_request_leaves_non_core_config_to_provider() -> None:
    config = {"raw": True}
    model = _model(api="custom-api", adapter=config)
    request = _request(model)

    assert normalize_provider_request_for_api("custom-api", request) is request
