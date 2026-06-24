from __future__ import annotations

import inspect
from dataclasses import replace

import pytest

from loushang.ai.model import (
    AnthropicMessagesConfig,
    Auth,
    Endpoint,
    EndpointRouting,
    EndpointTransport,
    Model,
    ModelRegistry,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
    Pricing,
    Provider,
)


def test_openai_completions_adapter_round_trip() -> None:
    adapter = OpenAICompletionsConfig.from_raw(
        {
            "store": False,
            "developerRole": False,
            "streamingUsage": True,
            "maxOutputTokensField": "max_tokens",
            "reasoningEffort": True,
            "reasoningEffortMap": {"off": None, "minimal": "low"},
            "strictSchema": True,
            "promptCacheKey": True,
            "longCacheRetention": False,
            "sessionAffinityHeaders": True,
            "toolResultName": True,
            "assistantAfterToolResult": True,
            "thinkingAsText": True,
            "assistantReasoningContent": True,
            "toolStream": True,
            "reasoningFormat": "moonshot",
            "cacheControlFormat": "anthropic",
            "extraBody": {"metadata": {"owner": "tests"}},
        }
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        adapter=adapter,
    )

    raw = endpoint.to_raw()["adapter"]

    assert raw == {
        "store": False,
        "developerRole": False,
        "streamingUsage": True,
        "maxOutputTokensField": "max_tokens",
        "reasoningEffort": True,
        "reasoningEffortMap": {"off": None, "minimal": "low"},
        "strictSchema": True,
        "promptCacheKey": True,
        "longCacheRetention": False,
        "sessionAffinityHeaders": True,
        "toolResultName": True,
        "assistantAfterToolResult": True,
        "thinkingAsText": True,
        "assistantReasoningContent": True,
        "toolStream": True,
        "reasoningFormat": "moonshot",
        "cacheControlFormat": "anthropic",
        "extraBody": {"metadata": {"owner": "tests"}},
    }
    assert OpenAICompletionsConfig.from_raw(raw) == adapter


def test_openai_completions_adapter_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="adapter config field must be a boolean"):
        OpenAICompletionsConfig(strict_schema="yes")
    with pytest.raises(
        ValueError, match="adapter config field must be a non-empty string"
    ):
        OpenAICompletionsConfig(max_output_tokens_field="")
    with pytest.raises(ValueError, match="adapter config has unknown keys"):
        OpenAICompletionsConfig.from_raw({"futureFlag": True})


def test_openai_completions_extra_body_rejects_sdk_fields() -> None:
    with pytest.raises(ValueError, match="cannot override SDK field"):
        OpenAICompletionsConfig.from_raw({"extraBody": {"model": "other"}})
    with pytest.raises(ValueError, match="JSON-safe"):
        OpenAICompletionsConfig.from_raw({"extraBody": {"bad": object()}})


def test_openai_responses_adapter_round_trip() -> None:
    adapter = OpenAIResponsesConfig.from_raw(
        {
            "developerRole": False,
            "assistantAfterToolResult": True,
            "promptCacheKey": False,
            "longCacheRetention": False,
            "sessionIdHeader": False,
            "sessionAffinityHeaders": True,
        }
    )
    endpoint = Endpoint(
        id="openai-responses",
        provider="custom",
        api="openai-responses",
        adapter=adapter,
    )

    raw = endpoint.to_raw()["adapter"]

    assert raw == {
        "developerRole": False,
        "assistantAfterToolResult": True,
        "promptCacheKey": False,
        "longCacheRetention": False,
        "sessionIdHeader": False,
        "sessionAffinityHeaders": True,
    }
    assert OpenAIResponsesConfig.from_raw(raw) == adapter


def test_openai_responses_adapter_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="adapter config field must be a boolean"):
        OpenAIResponsesConfig(prompt_cache_key="yes")
    with pytest.raises(ValueError, match="adapter config has unknown keys"):
        OpenAIResponsesConfig.from_raw({"reasoningFormat": "openai"})


def test_anthropic_messages_adapter_round_trip() -> None:
    adapter = AnthropicMessagesConfig.from_raw(
        {
            "fineGrainedTools": True,
            "interleavedThinking": False,
            "sessionAffinityHeaders": True,
            "longCacheRetention": False,
        }
    )
    endpoint = Endpoint(
        id="anthropic-messages",
        provider="custom",
        api="anthropic-messages",
        adapter=adapter,
    )

    raw = endpoint.to_raw()["adapter"]

    assert raw == {
        "sessionAffinityHeaders": True,
        "longCacheRetention": False,
        "fineGrainedTools": True,
        "interleavedThinking": False,
    }
    assert AnthropicMessagesConfig.from_raw(raw) == adapter


def test_anthropic_messages_adapter_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="adapter config field must be a boolean"):
        AnthropicMessagesConfig(long_cache_retention="yes")
    with pytest.raises(ValueError, match="adapter config has unknown keys"):
        AnthropicMessagesConfig.from_raw({"developerRole": False})


def test_model_adapter_override_merges_endpoint_adapter() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        adapter=OpenAICompletionsConfig(
            developer_role=False,
            max_output_tokens_field="max_tokens",
        ),
    )
    model = Model(
        id="public-model",
        provider="custom",
        endpoint="openai-completions",
        adapter=OpenAICompletionsConfig(reasoning_format="moonshot"),
    )

    bound = ModelRegistry.from_providers(
        {
            "custom": Provider(
                id="custom",
                endpoints={endpoint.id: replace(endpoint, models={model.id: model})},
            )
        }
    ).get_model("custom", "openai-completions", model.id)

    assert isinstance(bound.adapter, OpenAICompletionsConfig)
    assert bound.adapter.developer_role is False
    assert bound.adapter.reasoning_format == "moonshot"


def test_model_adapter_raw_override_can_restore_default_value() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        adapter=OpenAICompletionsConfig(developer_role=False),
    )
    model = Model(
        id="public-model",
        provider="custom",
        endpoint="openai-completions",
        adapter=OpenAICompletionsConfig.from_raw({"developerRole": True}),
    )

    bound = ModelRegistry.from_providers(
        {
            "custom": Provider(
                id="custom",
                endpoints={endpoint.id: replace(endpoint, models={model.id: model})},
            )
        }
    ).get_model("custom", "openai-completions", model.id)

    assert isinstance(bound.adapter, OpenAICompletionsConfig)
    assert bound.adapter.developer_role is True


def test_endpoint_transport_round_trip() -> None:
    transport = EndpointTransport.from_raw(
        {
            "kind": "httpx",
            "stream": "sse",
            "fallback": True,
            "timeout": 30,
        }
    )
    endpoint = Endpoint(
        id="anthropic-messages",
        provider="custom",
        api="anthropic-messages",
        transport=transport,
    )

    raw = endpoint.to_raw()["transport"]

    assert raw == {
        "kind": "httpx",
        "stream": "sse",
        "fallback": True,
        "timeout": 30,
    }
    assert EndpointTransport.from_raw(raw) == transport


def test_endpoint_transport_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="transport field must be a non-empty string"):
        EndpointTransport(kind="")
    with pytest.raises(ValueError, match="transport field must be a boolean"):
        EndpointTransport(fallback="yes")


@pytest.mark.parametrize("timeout", [0, float("nan"), float("inf"), float("-inf")])
def test_endpoint_transport_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="transport field must be a positive number"):
        EndpointTransport(timeout=timeout)
    with pytest.raises(ValueError, match="transport field must be a positive number"):
        EndpointTransport.from_raw({"timeout": timeout})


def test_endpoint_routing_round_trip_defensively_copies_raw() -> None:
    routing = EndpointRouting.from_raw(
        {
            "requestOverrides": {
                "openrouter": {"only": ["anthropic"]},
                "vercelGateway": {"order": ["openai", "anthropic"]},
            }
        }
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        routing=routing,
    )

    raw = endpoint.to_raw()["routing"]
    raw["requestOverrides"]["openrouter"]["only"].append("openai")

    assert routing.to_raw() == {
        "requestOverrides": {
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    }
    assert EndpointRouting.from_raw(endpoint.to_raw()["routing"]) == routing


def test_endpoint_routing_rejects_invalid_request_overrides() -> None:
    with pytest.raises(ValueError, match="routing field must be an object"):
        EndpointRouting.from_raw({"requestOverrides": True})
    with pytest.raises(ValueError, match="requestOverrides entries must be objects"):
        EndpointRouting.from_raw({"requestOverrides": {"openrouter": True}})


def test_model_omits_unknown_pricing_from_raw() -> None:
    model = Model(id="public-model", provider="custom", endpoint="openai-completions")

    raw = model.to_raw()

    assert model.pricing is None
    assert "pricing" not in raw


def test_provider_endpoint_and_model_to_raw_include_optional_fields() -> None:
    model = Model(
        id="public-model",
        provider="custom",
        endpoint="openai-completions",
        name="Public Model",
        family="test",
        alias="public",
        knowledge="2026-01",
        release_date="2026-01-01",
        last_updated="2026-02-01",
        auth=Auth(api_key_env="MODEL_KEY"),
        adapter=OpenAICompletionsConfig(reasoning_format="moonshot"),
        pricing=Pricing(input=1, output=2),
        transport=EndpointTransport(kind="httpx"),
        routing=EndpointRouting.from_raw(
            {"requestOverrides": {"openrouter": {"order": ["moonshot"]}}}
        ),
    )
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        name="OpenAI-compatible",
        base_url="https://example.test/v1",
        base_url_env="CUSTOM_BASE_URL",
        region="global",
        lane="coding",
        preferred=True,
        docs="https://example.test/docs",
        auth=Auth(api_key_env="ENDPOINT_KEY"),
        adapter=OpenAICompletionsConfig(developer_role=False),
        models={"public-model": model},
    )
    provider = Provider(
        id="custom",
        name="Custom",
        website="https://example.test",
        auth=Auth(api_key_env="PROVIDER_KEY"),
        endpoints={endpoint.id: endpoint},
    )

    raw = provider.to_raw()

    assert provider.get_endpoint("openai-completions") == endpoint
    assert provider.get_model("openai-completions", "public-model") == model
    assert provider.get_model("missing", "public-model") is None
    assert provider.list_models() == [model]
    assert raw["displayName"] == "Custom"
    assert raw["website"] == "https://example.test"
    endpoint_raw = raw["endpoints"]["openai-completions"]
    assert endpoint_raw["displayName"] == "OpenAI-compatible"
    assert endpoint_raw["baseUrl"] == "https://example.test/v1"
    assert endpoint_raw["baseUrlEnv"] == "CUSTOM_BASE_URL"
    assert endpoint_raw["region"] == "global"
    assert endpoint_raw["lane"] == "coding"
    assert endpoint_raw["preferred"] is True
    assert endpoint_raw["docs"] == "https://example.test/docs"
    model_raw = endpoint_raw["models"]["public-model"]
    assert model_raw["adapter"]["reasoningFormat"] == "moonshot"
    assert model_raw["pricing"] == {"input": 1, "output": 2}
    assert model_raw["auth"]["apiKeyEnv"] == "MODEL_KEY"
    assert model_raw["transport"] == {"kind": "httpx"}
    assert model_raw["routing"] == {
        "requestOverrides": {"openrouter": {"order": ["moonshot"]}}
    }


def test_auth_to_raw_omits_empty_optional_fields() -> None:
    assert Auth(kind="oauth").to_raw() == {"kind": "oauth"}
    partial = Auth.from_raw({"extraHeaders": {"x-extra": "yes"}})
    assert partial is not None
    assert partial.to_raw() == {"extraHeaders": {"x-extra": "yes"}}
    assert Auth(
        kind="apiKey",
        api_key_env="PRIMARY_KEY",
        api_key_envs=("SECONDARY_KEY",),
        header="X-Key",
        prefix="",
        extra_headers={"x-extra": "yes"},
    ).to_raw() == {
        "apiKeyEnv": "PRIMARY_KEY",
        "apiKeyEnvs": ["SECONDARY_KEY"],
        "header": "X-Key",
        "prefix": "",
        "extraHeaders": {"x-extra": "yes"},
    }


def test_pricing_round_trip_preserves_unknown_and_zero_components() -> None:
    pricing = Pricing.from_raw({"input": 0, "output": 2.0})

    assert pricing == Pricing(input=0, output=2.0)
    assert pricing.cache_read is None
    assert pricing.cache_write is None
    assert pricing.to_raw() == {"input": 0, "output": 2.0}


def test_model_upstream_id_round_trip() -> None:
    model = Model(
        id="public-model",
        provider="custom",
        endpoint="openai-completions",
        upstream_id="vendor/public-model:latest",
    )

    raw = model.to_raw()

    assert raw["upstreamId"] == "vendor/public-model:latest"
    assert "upstreamModelId" not in raw


def test_model_constructor_keeps_existing_fields_before_upstream_id() -> None:
    parameters = list(inspect.signature(Model).parameters)

    assert parameters.index("knowledge") < parameters.index("upstream_id")
    assert parameters.index("routing") < parameters.index("upstream_id")


def test_model_rejects_invalid_upstream_id() -> None:
    with pytest.raises(ValueError, match="upstream_id must be a non-empty string"):
        Model(
            id="public-model",
            provider="custom",
            endpoint="openai-completions",
            upstream_id="",
        )
    with pytest.raises(ValueError, match="upstream_id must be a non-empty string"):
        Model(
            id="public-model",
            provider="custom",
            endpoint="openai-completions",
            upstream_id=" ",
        )
