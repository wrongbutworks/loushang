from __future__ import annotations

import asyncio
import inspect
import json
import os
from dataclasses import asdict, fields

import pytest

import loushang.ai.model.registry as model_registry_module
from loushang.ai.advanced import OpenAICompletionsOptions
from loushang.ai.contrib.openai_codex.provider import OpenAICodexResponsesProvider
from loushang.ai.contrib.openai_codex.runtime_config import (
    OpenAICodexRuntimeConfig,
    resolve_openai_codex_runtime_config,
)
from loushang.ai.model import (
    Auth,
    Capabilities,
    Compat,
    Defaults,
    Endpoint,
    EndpointProtocolFeatures,
    EndpointRouting,
    EndpointTransport,
    EndpointWireDialect,
    Model,
    ModelRegistry,
    Provider,
    SupportStatus,
)
from loushang.ai.model.compat_schema import (
    CACHE_CONTROL_FORMAT,
    FINE_GRAINED_TOOLS,
    INTERLEAVED_THINKING,
    MAX_TOKENS_FIELD,
    OPENROUTER_ROUTING,
    REASONING_EFFORT_MAP,
    SEND_SESSION_AFFINITY_HEADERS,
    SUPPORTS_CACHE_CONTROL_ON_TOOLS,
    SUPPORTS_DEVELOPER_ROLE,
    SUPPORTS_EAGER_TOOL_INPUT_STREAMING,
    SUPPORTS_LONG_CACHE_RETENTION,
    SUPPORTS_PROMPT_CACHE_KEY,
    SUPPORTS_REASONING_EFFORT,
    SUPPORTS_STORE,
    SUPPORTS_STREAM_REASONING_DELTA,
    SUPPORTS_STRICT_MODE,
    THINKING_FORMAT,
    VERCEL_GATEWAY_ROUTING,
    resolve_anthropic_messages_compat,
    resolve_openai_completions_compat,
)
from loushang.ai.model.loader import load_model_registry, load_model_registry_from_file
from loushang.ai.model.registry import (
    clear_default_model_registry,
    get_default_model_registry,
    resolve_model_api,
    resolve_model_endpoint,
)
from loushang.ai.options import CallOptions, ReasoningOptions
from loushang.ai.provider import (
    AdapterRuntimeConfig,
    ResolvedEndpoint,
    ResolvedRequest,
    resolve_endpoint_for_model,
    resolve_provider_request,
    resolve_request_for_model,
)
from loushang.ai.provider.invocation import (
    call_api_provider_stream,
)

OPENAI_CODEX_RESPONSES_API = OpenAICodexResponsesProvider.api
OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER = resolve_openai_codex_runtime_config


def test_openai_completions_stream_reasoning_delta_defaults_to_bool() -> None:
    compat = resolve_openai_completions_compat()

    assert compat[SUPPORTS_STREAM_REASONING_DELTA] is False


def test_standard_compat_profiles_are_identity_free() -> None:
    standard = resolve_openai_completions_compat()
    anthropic_standard = resolve_anthropic_messages_compat()

    assert standard[SUPPORTS_DEVELOPER_ROLE] is True
    assert standard[SUPPORTS_REASONING_EFFORT] is True
    assert standard[MAX_TOKENS_FIELD] == "max_completion_tokens"
    assert standard[THINKING_FORMAT] == "openai"
    assert SUPPORTS_PROMPT_CACHE_KEY not in standard
    assert anthropic_standard[SUPPORTS_EAGER_TOOL_INPUT_STREAMING] is True
    assert anthropic_standard[SUPPORTS_LONG_CACHE_RETENTION] is True


def test_openai_completions_compat_uses_only_explicit_raw_overrides() -> None:
    compat = resolve_openai_completions_compat(
        raw={MAX_TOKENS_FIELD: "max_tokens"},
    )

    assert compat[MAX_TOKENS_FIELD] == "max_tokens"
    assert compat[SUPPORTS_DEVELOPER_ROLE] is True
    assert compat[SUPPORTS_STORE] is True
    assert compat[THINKING_FORMAT] == "openai"


def test_custom_openai_completions_endpoint_without_explicit_contract_uses_standard_profile(
    tmp_path,
) -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "baseUrl": "https://api.moonshot.cn/v1",
                        "models": {
                            "kimi-k2.5": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        }
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "kimi-k2.5")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat[MAX_TOKENS_FIELD] == "max_completion_tokens"
    assert resolved.adapter_compat[SUPPORTS_DEVELOPER_ROLE] is True
    assert resolved.adapter_compat[THINKING_FORMAT] == "openai"


def test_schema_v2_custom_openai_completions_requires_explicit_contract(
    tmp_path,
) -> None:
    raw = {
        "schemaVersion": 2,
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "baseUrl": "https://api.moonshot.cn/v1",
                        "models": {
                            "kimi-k2.5": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        },
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="must declare protocol or dialect"):
        load_model_registry_from_file(path)


def test_schema_v2_custom_openai_completions_base_url_env_requires_contract(
    tmp_path,
) -> None:
    raw = {
        "schemaVersion": 2,
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "baseUrlEnv": "CUSTOM_OPENAI_BASE_URL",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        },
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="must declare protocol or dialect"):
        load_model_registry_from_file(path)


def test_custom_openai_completions_endpoint_prompt_cache_key_is_opt_in() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://example.compat/v1",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})
    provider_resolved = resolve_provider_request(
        "openai-completions",
        model,
        request=resolved,
    )

    assert resolved.adapter_compat.get(SUPPORTS_PROMPT_CACHE_KEY, False) is False
    assert resolved.adapter_protocol.cache.prompt_key is SupportStatus.UNKNOWN
    assert provider_resolved.adapter_protocol.cache.prompt_key is SupportStatus.UNKNOWN


def test_custom_openai_completions_prompt_cache_key_projects_to_protocol() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://example.compat/v1",
        compat=Compat.from_raw({SUPPORTS_PROMPT_CACHE_KEY: True}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat[SUPPORTS_PROMPT_CACHE_KEY] is True
    assert resolved.adapter_protocol.cache.prompt_key is SupportStatus.SUPPORTED


def test_official_openai_completions_url_does_not_project_prompt_cache_key() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://api.openai.com/v1",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})
    provider_resolved = resolve_provider_request(
        "openai-completions",
        model,
        request=resolved,
    )

    assert SUPPORTS_PROMPT_CACHE_KEY not in resolved.adapter_compat
    assert resolved.adapter_protocol.cache.prompt_key is SupportStatus.UNKNOWN
    assert provider_resolved.adapter_protocol.cache.prompt_key is SupportStatus.UNKNOWN


def test_official_openai_completions_prompt_cache_key_can_be_disabled() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://api.openai.com/v1",
        compat=Compat.from_raw({SUPPORTS_PROMPT_CACHE_KEY: False}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat[SUPPORTS_PROMPT_CACHE_KEY] is False
    assert resolved.adapter_protocol.cache.prompt_key is SupportStatus.UNSUPPORTED


def test_builtin_catalog_declares_curated_openai_compat_bridge_facts() -> None:
    registry = get_default_model_registry()
    cases = [
        (
            ("moonshot", "openai-completions", "kimi-k2.6"),
            {
                "supportsStore": False,
                "supportsDeveloperRole": False,
                "supportsReasoningEffort": False,
                "maxTokensField": "max_tokens",
                "supportsStrictMode": False,
                "thinkingFormat": "moonshot",
            },
        ),
        (
            ("deepseek", "openai-completions", "deepseek-v4-flash"),
            {
                "supportsStore": False,
                "supportsDeveloperRole": False,
                "supportsReasoningEffort": True,
                "maxTokensField": "max_tokens",
                "supportsStrictMode": True,
                "thinkingFormat": "deepseek",
                "requiresReasoningContentOnAssistantMessages": True,
            },
        ),
        (
            ("stepfun", "openai-completions", "step-3.7-flash"),
            {
                "supportsStore": False,
                "supportsDeveloperRole": False,
                "supportsReasoningEffort": True,
                "reasoningEffortMap": {
                    "low": "low",
                    "medium": "medium",
                    "high": "high",
                    "xhigh": "high",
                },
                "maxTokensField": "max_tokens",
                "supportsStrictMode": False,
                "thinkingFormat": "openai",
            },
        ),
        (
            ("baidu-qianfan", "openai-completions-cn", "ernie-5.1"),
            {
                "supportsStore": False,
                "supportsDeveloperRole": False,
                "supportsReasoningEffort": False,
                "maxTokensField": "max_tokens",
                "supportsStrictMode": False,
                "thinkingFormat": "openai",
            },
        ),
        (
            ("zai", "openai-completions", "glm-5.2"),
            {
                "supportsStore": False,
                "supportsDeveloperRole": False,
                "supportsReasoningEffort": False,
                "maxTokensField": "max_tokens",
                "supportsStrictMode": False,
                "thinkingFormat": "zai-thinking",
            },
        ),
    ]

    for spec, expected in cases:
        model = registry.get_model(*spec)
        assert model is not None
        resolved = resolve_request_for_model(
            model,
            registry=registry,
            env={
                "CLOUDFLARE_ACCOUNT_ID": "example-account",
                "CLOUDFLARE_GATEWAY_ID": "example-gateway",
            },
        )

        assert {key: resolved.adapter_compat.get(key) for key in expected} == expected


def test_builtin_openai_compatible_endpoints_do_not_declare_prompt_cache_key() -> None:
    registry = get_default_model_registry()
    env = {
        "CLOUDFLARE_ACCOUNT_ID": "example-account",
        "CLOUDFLARE_GATEWAY_ID": "example-gateway",
        "GOOGLE_CLOUD_PROJECT": "example-project",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
    }

    for endpoint in registry.list_endpoints():
        if endpoint.api != "openai-completions" or endpoint.provider_id == "openai":
            continue
        for model_id in endpoint.models:
            model = registry.get_model(endpoint.provider_id, endpoint.id, model_id)
            resolved = resolve_request_for_model(model, registry=registry, env=env)

            assert (
                resolved.adapter_compat.get(SUPPORTS_PROMPT_CACHE_KEY, False) is False
            ), (
                endpoint.provider_id,
                endpoint.id,
                model_id,
            )
            assert SUPPORTS_PROMPT_CACHE_KEY not in resolved.adapter_compat, (
                endpoint.provider_id,
                endpoint.id,
                model_id,
            )


def test_builtin_catalog_declares_curated_anthropic_compat_bridge_facts() -> None:
    registry = get_default_model_registry()
    cases = [
        (
            "anthropic",
            "anthropic-messages",
            "claude-sonnet-4-6",
            {
                "sendSessionAffinityHeaders": False,
                "supportsEagerToolInputStreaming": True,
                "supportsCacheControlOnTools": True,
                "supportsLongCacheRetention": True,
                "fineGrainedTools": True,
                "interleavedThinking": True,
            },
        ),
        (
            "minimax",
            "anthropic-messages",
            "MiniMax-M3",
            {
                "sendSessionAffinityHeaders": False,
                "supportsEagerToolInputStreaming": True,
                "supportsCacheControlOnTools": True,
                "supportsLongCacheRetention": True,
            },
        ),
    ]

    for provider_id, endpoint_id, model_id, expected in cases:
        model = registry.get_model(provider_id, endpoint_id, model_id)
        resolved = resolve_request_for_model(model, registry=registry, env={})

        assert {key: resolved.adapter_compat.get(key) for key in expected} == expected


def test_resolver_constructor_keeps_existing_fields_before_upstream_model_id() -> None:
    endpoint_parameters = list(inspect.signature(ResolvedEndpoint).parameters)
    request_parameters = list(inspect.signature(ResolvedRequest).parameters)

    assert endpoint_parameters[:8] == [
        "provider",
        "endpoint",
        "api",
        "base_url",
        "base_url_env",
        "regions",
        "default_region",
        "compat",
    ]
    assert endpoint_parameters.index("routing") < endpoint_parameters.index(
        "upstream_model_id"
    )
    assert endpoint_parameters.index("upstream_model_id") < endpoint_parameters.index(
        "protocol"
    )
    assert endpoint_parameters.index("dialect") < endpoint_parameters.index(
        "adapter_compat"
    )
    assert request_parameters[:8] == [
        "provider",
        "endpoint",
        "api",
        "base_url",
        "region",
        "candidate_base_urls",
        "headers",
        "compat",
    ]
    assert request_parameters.index("temperature") < request_parameters.index(
        "upstream_model_id"
    )
    assert request_parameters.index("upstream_model_id") < request_parameters.index(
        "protocol"
    )
    assert request_parameters.index("capabilities") < request_parameters.index(
        "adapter_protocol"
    )


def test_model_constructor_keeps_endpoint_snapshot_fields_private() -> None:
    parameters = inspect.signature(Model).parameters

    assert "_endpoint_ref" not in parameters


def test_resolved_request_accepts_deprecated_compat_init_alias() -> None:
    endpoint = ResolvedEndpoint(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        compat={"supportsDeveloperRole": False},
    )
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url=None,
        compat={"maxTokensField": "max_tokens"},
    )

    assert endpoint.adapter_compat == {"supportsDeveloperRole": False}
    assert endpoint.compat == {"supportsDeveloperRole": False}
    assert request.adapter_compat == {"maxTokensField": "max_tokens"}
    assert request.compat == {"maxTokensField": "max_tokens"}


def test_resolve_provider_request_validates_supplied_request_api() -> None:
    model = Model(id="model-a", provider="custom", endpoint="openai-responses")
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-responses",
        api="openai-completions",
        base_url=None,
    )

    with pytest.raises(ValueError, match="Mismatched api"):
        resolve_provider_request("openai-responses", model, request=request)


def test_resolve_provider_request_normalizes_supplied_openai_responses_request() -> (
    None
):
    model = Model(id="model-a", provider="custom", endpoint="openai-responses")
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-responses",
        api="openai-responses",
        base_url=None,
    )

    resolved = resolve_provider_request("openai-responses", model, request=request)

    assert resolved is not request
    assert resolved.adapter_protocol.roles.developer is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.cache.long_retention is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.session.id_header is SupportStatus.SUPPORTED
    assert resolved.adapter_dialect.tools.assistant_bridge_required is False


def test_resolve_provider_request_openai_responses_typed_overrides_stale_compat() -> (
    None
):
    model = Model(id="model-a", provider="custom", endpoint="openai-responses")
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-responses",
        api="openai-responses",
        base_url=None,
        compat={
            "supportsDeveloperRole": True,
            "supportsLongCacheRetention": True,
            "sendSessionIdHeader": True,
            "requiresAssistantAfterToolResult": True,
        },
        adapter_protocol=EndpointProtocolFeatures.from_raw(
            {
                "roles": {"developer": "unsupported"},
                "cache": {"longRetention": "unsupported"},
                "session": {"idHeader": "unsupported"},
            }
        ),
        adapter_dialect=EndpointWireDialect.from_raw(
            {"tools": {"assistantBridgeRequired": False}}
        ),
    )

    resolved = resolve_provider_request("openai-responses", model, request=request)

    assert resolved.adapter_protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved.adapter_protocol.cache.long_retention is SupportStatus.UNSUPPORTED
    assert resolved.adapter_protocol.session.id_header is SupportStatus.UNSUPPORTED
    assert resolved.adapter_dialect.tools.assistant_bridge_required is False
    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["supportsLongCacheRetention"] is False
    assert resolved.adapter_compat["sendSessionIdHeader"] is False
    assert resolved.adapter_compat["requiresAssistantAfterToolResult"] is False


def test_resolve_provider_request_openai_codex_projects_compat_to_runtime_config() -> (
    None
):
    model = Model(id="model-a", provider="openai-codex", endpoint="openai-codex")
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api="openai-codex-responses",
        base_url=None,
        adapter_compat={
            "codexIncludeClientRequestId": False,
            "codexIncludeConversationId": True,
            "codexPromptCacheRetention": "ephemeral",
            "codexOriginator": "compat-test",
            "codexUserAgent": "compat-agent",
        },
    )

    resolved = resolve_provider_request(
        "openai-codex-responses",
        model,
        request=request,
        adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
    )

    assert isinstance(resolved.adapter_config, OpenAICodexRuntimeConfig)
    assert resolved.adapter_config.include_client_request_id is False
    assert resolved.adapter_config.include_conversation_id is True
    assert resolved.adapter_config.prompt_cache_retention == "ephemeral"
    assert resolved.adapter_config.originator == "compat-test"
    assert resolved.adapter_config.user_agent == "compat-agent"


def test_resolve_provider_request_openai_codex_rejects_conflicting_runtime_config() -> (
    None
):
    model = Model(id="model-a", provider="openai-codex", endpoint="openai-codex")
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api="openai-codex-responses",
        base_url=None,
        adapter_compat={
            "codexOriginator": "fresh",
            "codexUserAgent": "fresh-agent",
        },
        adapter_config=OpenAICodexRuntimeConfig(
            originator="stale",
            user_agent="stale-agent",
        ),
    )

    with pytest.raises(
        ValueError,
        match="adapter_config conflicts with adapter_compat",
    ):
        resolve_provider_request(
            "openai-codex-responses",
            model,
            request=request,
            adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
        )


def test_resolve_provider_request_openai_codex_keeps_runtime_config_input() -> None:
    model = Model(id="model-a", provider="openai-codex", endpoint="openai-codex")
    codex_config = OpenAICodexRuntimeConfig(
        originator="typed",
        user_agent="typed-agent",
    )
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api="openai-codex-responses",
        base_url=None,
        adapter_config=codex_config,
    )

    resolved = resolve_provider_request(
        "openai-codex-responses",
        model,
        request=request,
        adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
    )

    assert resolved.adapter_config == codex_config


def test_resolve_provider_request_openai_codex_rejects_foreign_runtime_config() -> None:
    model = Model(id="model-a", provider="openai-codex", endpoint="openai-codex")
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api=OPENAI_CODEX_RESPONSES_API,
        base_url=None,
        adapter_config=AdapterRuntimeConfig(),
    )

    with pytest.raises(
        TypeError,
        match="adapter_config for openai-codex-responses must be "
        "OpenAICodexRuntimeConfig",
    ):
        resolve_provider_request(
            OPENAI_CODEX_RESPONSES_API,
            model,
            request=request,
            adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
        )


def test_resolve_provider_request_unknown_api_preserves_runtime_config() -> None:
    model = Model(id="model-a", provider="custom", endpoint="custom-api")
    adapter_config = AdapterRuntimeConfig()
    request = ResolvedRequest(
        provider="custom",
        endpoint="custom-api",
        api="custom-api",
        base_url=None,
        adapter_config=adapter_config,
    )

    resolved = resolve_provider_request("custom-api", model, request=request)

    assert resolved.adapter_config is adapter_config


@pytest.mark.parametrize(
    ("config_kwargs", "message"),
    (
        (
            {"include_client_request_id": "false"},
            "include_client_request_id must be boolean",
        ),
        (
            {"include_conversation_id": "true"},
            "include_conversation_id must be boolean",
        ),
        (
            {"prompt_cache_retention": 123},
            "prompt_cache_retention must be non-empty string or None",
        ),
        (
            {"originator": ""},
            "originator must be non-empty string",
        ),
        (
            {"user_agent": None},
            "user_agent must be non-empty string",
        ),
    ),
)
def test_openai_codex_runtime_config_rejects_invalid_typed_values(
    config_kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        OpenAICodexRuntimeConfig(**config_kwargs)


def test_resolve_provider_request_openai_codex_compares_explicit_runtime_keys() -> None:
    model = Model(id="model-a", provider="openai-codex", endpoint="openai-codex")
    codex_config = OpenAICodexRuntimeConfig(
        originator="typed",
        user_agent="typed-agent",
    )
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api="openai-codex-responses",
        base_url=None,
        adapter_compat={
            "supportsDeveloperRole": True,
            "codexOriginator": "typed",
        },
        adapter_config=codex_config,
    )

    resolved = resolve_provider_request(
        "openai-codex-responses",
        model,
        request=request,
        adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
    )

    assert resolved.adapter_config == codex_config


def test_resolve_provider_request_openai_codex_rejects_invalid_runtime_config() -> None:
    model = Model(id="model-a", provider="openai-codex", endpoint="openai-codex")
    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api="openai-codex-responses",
        base_url=None,
        adapter_compat={
            "codexIncludeClientRequestId": "false",
        },
    )

    with pytest.raises(
        ValueError,
        match="codexIncludeClientRequestId must be boolean",
    ):
        resolve_provider_request(
            "openai-codex-responses",
            model,
            request=request,
            adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
        )

    request = ResolvedRequest(
        provider="openai-codex",
        endpoint="openai-codex",
        api="openai-codex-responses",
        base_url=None,
        adapter_compat={
            "codexUserAgent": 123,
        },
    )

    with pytest.raises(ValueError, match="codexUserAgent must be non-empty string"):
        resolve_provider_request(
            "openai-codex-responses",
            model,
            request=request,
            adapter_config_resolver=OPENAI_CODEX_RUNTIME_CONFIG_RESOLVER,
        )


def test_resolve_provider_request_normalizes_supplied_anthropic_request() -> None:
    model = Model(id="model-a", provider="custom", endpoint="anthropic-messages")
    request = ResolvedRequest(
        provider="custom",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url=None,
    )

    resolved = resolve_provider_request("anthropic-messages", model, request=request)

    assert resolved is not request
    assert resolved.adapter_protocol.tools.eager_input_stream is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.tools.fine_grained is SupportStatus.UNKNOWN
    assert resolved.adapter_protocol.cache.on_tools is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.cache.long_retention is SupportStatus.SUPPORTED
    assert (
        resolved.adapter_protocol.session.affinity_headers is SupportStatus.UNSUPPORTED
    )
    assert resolved.adapter_protocol.reasoning.interleaved is SupportStatus.UNKNOWN
    assert resolved.adapter_compat[SUPPORTS_EAGER_TOOL_INPUT_STREAMING] is True
    assert FINE_GRAINED_TOOLS not in resolved.adapter_compat
    assert resolved.adapter_compat[SUPPORTS_CACHE_CONTROL_ON_TOOLS] is True
    assert resolved.adapter_compat[SUPPORTS_LONG_CACHE_RETENTION] is True
    assert resolved.adapter_compat[SEND_SESSION_AFFINITY_HEADERS] is False


def test_resolve_provider_request_anthropic_typed_overrides_stale_compat() -> None:
    model = Model(id="model-a", provider="custom", endpoint="anthropic-messages")
    request = ResolvedRequest(
        provider="custom",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url=None,
        compat={
            SUPPORTS_EAGER_TOOL_INPUT_STREAMING: False,
            FINE_GRAINED_TOOLS: False,
            SUPPORTS_CACHE_CONTROL_ON_TOOLS: False,
            SUPPORTS_LONG_CACHE_RETENTION: False,
            SEND_SESSION_AFFINITY_HEADERS: False,
            INTERLEAVED_THINKING: False,
        },
        adapter_protocol=EndpointProtocolFeatures.from_raw(
            {
                "reasoning": {"interleaved": "supported"},
                "tools": {
                    "eagerInputStream": "supported",
                    "fineGrained": "supported",
                },
                "cache": {
                    "onTools": "supported",
                    "longRetention": "supported",
                },
                "session": {"affinityHeaders": "supported"},
            }
        ),
    )

    resolved = resolve_provider_request("anthropic-messages", model, request=request)

    assert resolved.adapter_protocol.reasoning.interleaved is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.tools.eager_input_stream is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.tools.fine_grained is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.cache.on_tools is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.cache.long_retention is SupportStatus.SUPPORTED
    assert resolved.adapter_protocol.session.affinity_headers is SupportStatus.SUPPORTED
    assert resolved.adapter_compat[INTERLEAVED_THINKING] is True
    assert resolved.adapter_compat[SUPPORTS_EAGER_TOOL_INPUT_STREAMING] is True
    assert resolved.adapter_compat[FINE_GRAINED_TOOLS] is True
    assert resolved.adapter_compat[SUPPORTS_CACHE_CONTROL_ON_TOOLS] is True
    assert resolved.adapter_compat[SUPPORTS_LONG_CACHE_RETENTION] is True
    assert resolved.adapter_compat[SEND_SESSION_AFFINITY_HEADERS] is True


def test_resolve_provider_request_anthropic_typed_contract_satisfies_legacy_profile() -> (
    None
):
    model = Model(id="model-a", provider="fireworks", endpoint="anthropic-messages")
    request = ResolvedRequest(
        provider="fireworks",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url="https://api.fireworks.ai/inference/v1",
        adapter_protocol=EndpointProtocolFeatures.from_raw(
            {
                "tools": {
                    "eagerInputStream": "unsupported",
                    "fineGrained": "unsupported",
                },
                "cache": {
                    "onTools": "unsupported",
                    "longRetention": "unsupported",
                },
                "session": {"affinityHeaders": "supported"},
            }
        ),
    )

    resolved = resolve_provider_request("anthropic-messages", model, request=request)

    assert (
        resolved.adapter_protocol.tools.eager_input_stream is SupportStatus.UNSUPPORTED
    )
    assert resolved.adapter_protocol.tools.fine_grained is SupportStatus.UNSUPPORTED
    assert resolved.adapter_protocol.cache.on_tools is SupportStatus.UNSUPPORTED
    assert resolved.adapter_protocol.cache.long_retention is SupportStatus.UNSUPPORTED
    assert resolved.adapter_protocol.session.affinity_headers is SupportStatus.SUPPORTED
    assert resolved.adapter_compat[SUPPORTS_EAGER_TOOL_INPUT_STREAMING] is False
    assert resolved.adapter_compat[FINE_GRAINED_TOOLS] is False
    assert resolved.adapter_compat[SUPPORTS_CACHE_CONTROL_ON_TOOLS] is False
    assert resolved.adapter_compat[SUPPORTS_LONG_CACHE_RETENTION] is False
    assert resolved.adapter_compat[SEND_SESSION_AFFINITY_HEADERS] is True


def test_resolve_provider_request_anthropic_legacy_interleaved_off() -> None:
    model = Model(id="model-a", provider="custom", endpoint="anthropic-messages")
    request = ResolvedRequest(
        provider="custom",
        endpoint="anthropic-messages",
        api="anthropic-messages",
        base_url=None,
        compat={INTERLEAVED_THINKING: "off"},
    )

    resolved = resolve_provider_request("anthropic-messages", model, request=request)

    assert resolved.adapter_protocol.reasoning.interleaved is SupportStatus.UNSUPPORTED
    assert resolved.adapter_compat[INTERLEAVED_THINKING] is False


@pytest.mark.parametrize(
    ("api", "compat", "message"),
    [
        (
            "openai-responses",
            {"supportsDeveloperRole": "yes"},
            "supportsDeveloperRole",
        ),
        (
            "anthropic-messages",
            {SUPPORTS_LONG_CACHE_RETENTION: "yes"},
            SUPPORTS_LONG_CACHE_RETENTION,
        ),
    ],
)
def test_resolve_provider_request_validates_supplied_adapter_compat(
    api: str,
    compat: dict[str, object],
    message: str,
) -> None:
    model = Model(id="model-a", provider="custom", endpoint=api)
    request = ResolvedRequest(
        provider="custom",
        endpoint=api,
        api=api,
        base_url=None,
        compat=compat,
    )

    with pytest.raises(ValueError, match=message):
        resolve_provider_request(api, model, request=request)


def test_call_api_provider_helpers_use_normalized_supplied_request() -> None:
    provider = _RequestRecordingProvider()
    model = Model(id="model-a", provider="custom", endpoint="openai-completions")
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url=None,
        protocol=EndpointProtocolFeatures.from_raw(
            {"cache": {"promptKey": "supported"}}
        ),
    )

    stream = asyncio.run(
        call_api_provider_stream(
            provider,
            model,
            {"messages": []},
            OpenAICompletionsOptions(),
            request,
        )
    )
    asyncio.run(stream.result())
    assert provider.stream_request is not None
    assert (
        provider.stream_request.adapter_protocol.cache.prompt_key
        is SupportStatus.SUPPORTED
    )


def test_resolve_provider_request_validates_supplied_compat() -> None:
    model = Model(id="model-a", provider="custom", endpoint="openai-completions")
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url=None,
        compat={SUPPORTS_PROMPT_CACHE_KEY: "true"},
    )

    with pytest.raises(ValueError, match=SUPPORTS_PROMPT_CACHE_KEY):
        resolve_provider_request("openai-completions", model, request=request)


class _RequestRecordingProvider:
    api = "openai-completions"

    def __init__(self) -> None:
        self.stream_request: ResolvedRequest | None = None

    async def stream_raw(self, request):
        self.stream_request = request.resolved
        yield {"type": "response_done"}


def test_resolved_request_rejects_conflicting_compat_aliases() -> None:
    with pytest.raises(TypeError, match="adapter_compat or compat"):
        ResolvedEndpoint(
            provider="custom",
            endpoint="openai-completions",
            api="openai-completions",
            compat={"supportsDeveloperRole": False},
            adapter_compat={"supportsDeveloperRole": True},
        )
    with pytest.raises(TypeError, match="adapter_compat or compat"):
        ResolvedRequest(
            provider="custom",
            endpoint="openai-completions",
            api="openai-completions",
            base_url=None,
            compat={"maxTokensField": "max_tokens"},
            adapter_compat={"maxTokensField": "max_completion_tokens"},
        )


def test_resolved_request_keeps_deprecated_compat_dataclass_field() -> None:
    endpoint = ResolvedEndpoint(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        compat={"supportsDeveloperRole": False},
    )
    request = ResolvedRequest(
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url=None,
        adapter_compat={"maxTokensField": "max_tokens"},
    )

    assert "compat" in {field.name for field in fields(ResolvedEndpoint)}
    assert "compat" in {field.name for field in fields(ResolvedRequest)}
    assert asdict(endpoint)["compat"] == {"supportsDeveloperRole": False}
    assert asdict(request)["compat"] == {"maxTokensField": "max_tokens"}


def test_resolved_request_accepts_deprecated_positional_compat_slot() -> None:
    endpoint = ResolvedEndpoint(
        "custom",
        "openai-completions",
        "openai-completions",
        None,
        None,
        {},
        None,
        {"supportsDeveloperRole": False},
    )
    request = ResolvedRequest(
        "custom",
        "openai-completions",
        "openai-completions",
        None,
        None,
        (),
        {},
        {"maxTokensField": "max_tokens"},
    )

    assert isinstance(endpoint.protocol, EndpointProtocolFeatures)
    assert endpoint.adapter_compat == {"supportsDeveloperRole": False}
    assert endpoint.compat == {"supportsDeveloperRole": False}
    assert isinstance(request.protocol, EndpointProtocolFeatures)
    assert request.adapter_compat == {"maxTokensField": "max_tokens"}
    assert request.compat == {"maxTokensField": "max_tokens"}


def test_openai_completions_compat_preserves_legacy_routing_overrides() -> None:
    compat = resolve_openai_completions_compat(
        raw={
            OPENROUTER_ROUTING: {"only": ["anthropic"]},
            THINKING_FORMAT: "openrouter",
            VERCEL_GATEWAY_ROUTING: {"order": ["openai", "anthropic"]},
        },
    )

    assert compat[OPENROUTER_ROUTING] == {"only": ["anthropic"]}
    assert compat[THINKING_FORMAT] == "openrouter"
    assert compat[VERCEL_GATEWAY_ROUTING] == {"order": ["openai", "anthropic"]}


def test_anthropic_messages_protocol_flags_default_to_bool_or_absent() -> None:
    compat = resolve_anthropic_messages_compat()

    assert FINE_GRAINED_TOOLS not in compat
    assert INTERLEAVED_THINKING not in compat


def test_anthropic_messages_protocol_flags_preserve_explicit_booleans() -> None:
    compat = resolve_anthropic_messages_compat(
        raw={INTERLEAVED_THINKING: True},
    )

    assert compat[INTERLEAVED_THINKING] is True


def test_resolve_request_uses_in_memory_endpoint_protocol_bridge() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        protocol=EndpointProtocolFeatures.from_raw(
            {
                "roles": {"developer": "unsupported"},
                "reasoning": {"effort": "unsupported"},
                "tools": {"strictSchema": "unsupported"},
            }
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved.protocol.reasoning.effort is SupportStatus.UNSUPPORTED
    assert resolved.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert resolved.compat == resolved.adapter_compat
    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["supportsReasoningEffort"] is False
    assert resolved.adapter_compat["supportsStrictMode"] is False


def test_resolve_request_does_not_infer_adapter_contract_from_endpoint_identity() -> (
    None
):
    endpoint = Endpoint(
        id="openai-completions",
        provider="moonshot",
        api="openai-completions",
        base_url="https://api.moonshot.ai/v1",
        models={
            "model-a": Model(
                id="model-a",
                provider="moonshot",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"moonshot": Provider(id="moonshot", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("moonshot", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat[MAX_TOKENS_FIELD] == "max_completion_tokens"
    assert resolved.adapter_compat[SUPPORTS_DEVELOPER_ROLE] is True
    assert resolved.adapter_compat[THINKING_FORMAT] == "openai"


def test_resolve_request_explicit_unknown_projects_to_adapter_compat() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="moonshot",
        api="openai-completions",
        base_url="https://api.moonshot.ai/v1",
        compat=Compat.from_raw(
            {
                SUPPORTS_STORE: False,
                SUPPORTS_REASONING_EFFORT: False,
                MAX_TOKENS_FIELD: "max_tokens",
                SUPPORTS_STRICT_MODE: False,
                THINKING_FORMAT: "moonshot",
            }
        ),
        protocol=EndpointProtocolFeatures.from_raw({"roles": {"developer": "unknown"}}),
        models={
            "model-a": Model(
                id="model-a",
                provider="moonshot",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"moonshot": Provider(id="moonshot", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("moonshot", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.protocol.roles.developer is SupportStatus.UNKNOWN
    assert resolved.adapter_protocol.roles.developer is SupportStatus.UNSUPPORTED


def test_resolve_request_rejects_non_bool_protocol_compat_override() -> None:
    model = Model(
        id="dynamic",
        provider="custom",
        endpoint="openai-completions",
        compat={"supportsReasoningEffort": "true"},
    )

    with pytest.raises(ValueError, match="supportsReasoningEffort"):
        resolve_request_for_model(
            model,
            registry=ModelRegistry.from_providers({}),
            env={},
        )


def test_resolve_request_rejects_non_bool_prompt_cache_key_override() -> None:
    model = Model(
        id="dynamic",
        provider="custom",
        endpoint="openai-completions",
        compat={SUPPORTS_PROMPT_CACHE_KEY: "false"},
    )

    with pytest.raises(ValueError, match=SUPPORTS_PROMPT_CACHE_KEY):
        resolve_request_for_model(
            model,
            registry=ModelRegistry.from_providers({}),
            env={},
        )


def test_resolve_request_rejects_non_bool_endpoint_protocol_compat() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        compat=Compat.from_raw({"supportsReasoningEffort": "true"}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    with pytest.raises(ValueError, match="supportsReasoningEffort"):
        resolve_request_for_model(model, registry=registry, env={})


def test_resolve_request_rejects_non_bool_endpoint_prompt_cache_key() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        compat=Compat.from_raw({SUPPORTS_PROMPT_CACHE_KEY: "false"}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    with pytest.raises(ValueError, match=SUPPORTS_PROMPT_CACHE_KEY):
        resolve_request_for_model(model, registry=registry, env={})


def test_resolve_request_rejects_non_string_dialect_compat_override() -> None:
    model = Model(
        id="dynamic",
        provider="custom",
        endpoint="openai-completions",
        compat={"maxTokensField": 123},
    )

    with pytest.raises(ValueError, match="maxTokensField"):
        resolve_request_for_model(
            model,
            registry=ModelRegistry.from_providers({}),
            env={},
        )


def test_resolve_request_accepts_none_for_optional_dialect_compat_override() -> None:
    model = Model(
        id="dynamic",
        provider="custom",
        endpoint="openai-completions",
        compat={
            THINKING_FORMAT: None,
            CACHE_CONTROL_FORMAT: None,
        },
    )

    resolved = resolve_request_for_model(
        model,
        registry=ModelRegistry.from_providers({}),
        env={},
    )

    assert resolved.adapter_compat[THINKING_FORMAT] is None
    assert resolved.adapter_compat[CACHE_CONTROL_FORMAT] is None
    assert resolved.adapter_dialect.reasoning.wire_format is None
    assert resolved.adapter_dialect.cache.control_format is None


def test_resolve_request_none_dialect_compat_clears_inherited_typed_dialect() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        dialect=EndpointWireDialect.from_raw(
            {
                "reasoning": {"wireFormat": "moonshot"},
                "cache": {"controlFormat": "anthropic"},
            }
        ),
        models={
            "dynamic": Model(
                id="dynamic",
                provider="custom",
                endpoint="openai-completions",
                compat={
                    THINKING_FORMAT: None,
                    CACHE_CONTROL_FORMAT: None,
                },
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "dynamic")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat[THINKING_FORMAT] is None
    assert resolved.adapter_compat[CACHE_CONTROL_FORMAT] is None
    assert resolved.dialect.reasoning.wire_format is None
    assert resolved.dialect.cache.control_format is None
    assert resolved.adapter_dialect.reasoning.wire_format is None
    assert resolved.adapter_dialect.cache.control_format is None


def test_resolve_request_rejects_invalid_reasoning_effort_map_override() -> None:
    model = Model(
        id="dynamic",
        provider="custom",
        endpoint="openai-completions",
        compat={REASONING_EFFORT_MAP: {"low": 1}},
    )

    with pytest.raises(ValueError, match=REASONING_EFFORT_MAP):
        resolve_request_for_model(
            model,
            registry=ModelRegistry.from_providers({}),
            env={},
        )


def test_resolve_request_uses_in_memory_endpoint_dialect_bridge() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        dialect=EndpointWireDialect.from_raw(
            {
                "maxOutputTokensField": "max_completion_tokens",
                "tools": {
                    "resultNameRequired": True,
                    "assistantBridgeRequired": True,
                    "streamFlag": True,
                },
                "reasoning": {
                    "wireFormat": "moonshot",
                    "thinkingAsText": True,
                    "assistantContentRequired": True,
                },
                "cache": {"controlFormat": "anthropic"},
            }
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.dialect.max_output_tokens_field == "max_completion_tokens"
    assert resolved.dialect.tools.result_name_required is True
    assert resolved.dialect.tools.assistant_bridge_required is True
    assert resolved.dialect.tools.stream_flag is True
    assert resolved.dialect.reasoning.wire_format == "moonshot"
    assert resolved.dialect.reasoning.thinking_as_text is True
    assert resolved.dialect.reasoning.assistant_content_required is True
    assert resolved.dialect.cache.control_format == "anthropic"
    assert resolved.adapter_compat["maxTokensField"] == "max_completion_tokens"
    assert resolved.adapter_compat["requiresToolResultName"] is True
    assert resolved.adapter_compat["requiresAssistantAfterToolResult"] is True
    assert resolved.adapter_compat["requiresThinkingAsText"] is True
    assert (
        resolved.adapter_compat["requiresReasoningContentOnAssistantMessages"] is True
    )
    assert resolved.adapter_compat["thinkingFormat"] == "moonshot"
    assert resolved.adapter_compat["zaiToolStream"] is True
    assert resolved.adapter_compat["cacheControlFormat"] == "anthropic"


def test_resolve_endpoint_uses_in_memory_endpoint_dialect_bridge() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        dialect=EndpointWireDialect.from_raw(
            {
                "maxOutputTokensField": "max_completion_tokens",
                "tools": {
                    "resultNameRequired": True,
                    "assistantBridgeRequired": True,
                    "streamFlag": True,
                },
                "reasoning": {
                    "wireFormat": "moonshot",
                    "thinkingAsText": True,
                    "assistantContentRequired": True,
                },
                "cache": {"controlFormat": "anthropic"},
            }
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_endpoint_for_model(model, registry=registry)

    assert resolved.dialect.max_output_tokens_field == "max_completion_tokens"
    assert resolved.dialect.tools.result_name_required is True
    assert resolved.dialect.tools.assistant_bridge_required is True
    assert resolved.dialect.tools.stream_flag is True
    assert resolved.dialect.reasoning.wire_format == "moonshot"
    assert resolved.dialect.reasoning.thinking_as_text is True
    assert resolved.dialect.reasoning.assistant_content_required is True
    assert resolved.dialect.cache.control_format == "anthropic"
    assert resolved.adapter_compat["maxTokensField"] == "max_completion_tokens"
    assert resolved.adapter_compat["requiresToolResultName"] is True
    assert resolved.adapter_compat["requiresAssistantAfterToolResult"] is True
    assert resolved.adapter_compat["requiresThinkingAsText"] is True
    assert (
        resolved.adapter_compat["requiresReasoningContentOnAssistantMessages"] is True
    )
    assert resolved.adapter_compat["thinkingFormat"] == "moonshot"
    assert resolved.adapter_compat["zaiToolStream"] is True
    assert resolved.adapter_compat["cacheControlFormat"] == "anthropic"


def test_resolve_endpoint_projects_programmatic_compat_to_typed_contract() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        compat=Compat.from_raw(
            {
                "supportsDeveloperRole": False,
                "thinkingFormat": "moonshot",
            }
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_endpoint_for_model(model, registry=registry)

    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved.dialect.reasoning.wire_format == "moonshot"
    assert resolved.compat == resolved.adapter_compat
    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["thinkingFormat"] == "moonshot"


def test_resolve_request_exposes_in_memory_endpoint_transport_routing() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        transport=EndpointTransport(kind="httpx", stream="sse"),
        routing=EndpointRouting(
            request_overrides={
                "openrouter": {"only": ["anthropic"]},
                "vercelGateway": {"order": ["openai", "anthropic"]},
            }
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.transport == EndpointTransport(kind="httpx", stream="sse")
    assert resolved.routing == EndpointRouting(
        request_overrides={
            "openrouter": {"only": ["anthropic"]},
            "vercelGateway": {"order": ["openai", "anthropic"]},
        }
    )
    assert "openRouterRouting" not in resolved.adapter_compat
    assert "vercelGatewayRouting" not in resolved.adapter_compat


def test_resolve_request_uses_bound_transport_routing_with_empty_registry() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        transport=EndpointTransport(kind="httpx"),
        routing=EndpointRouting(
            request_overrides={"openrouter": {"only": ["anthropic"]}}
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=ModelRegistry.from_providers({}),
        env={},
    )

    assert resolved.transport == EndpointTransport(kind="httpx")
    assert resolved.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["anthropic"]}}
    )


def test_resolve_request_does_not_use_stale_bound_endpoint_transport_routing() -> None:
    old_endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        transport=EndpointTransport(timeout=10),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["old"]}}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    new_endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        transport=EndpointTransport(timeout=20),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["new"]}}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    old_registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={old_endpoint.id: old_endpoint})}
    )
    new_registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={new_endpoint.id: new_endpoint})}
    )
    model = old_registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=new_registry, env={})

    assert resolved.transport == EndpointTransport(timeout=20)
    assert resolved.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["new"]}}
    )


def test_resolve_request_ignores_direct_model_legacy_transport_routing() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="openrouter",
        api="openai-completions",
        base_url="https://openrouter.ai/api/v1",
        compat=Compat.from_raw({THINKING_FORMAT: "openrouter"}),
    )
    registry = ModelRegistry.from_providers(
        {"openrouter": Provider(id="openrouter", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="dynamic",
        provider="openrouter",
        endpoint="openai-completions",
        compat={
            "providerTransport": "httpx",
            "openRouterRouting": {"only": ["anthropic"]},
            "vercelGatewayRouting": {"order": ["openai", "anthropic"]},
        },
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.transport == EndpointTransport()
    assert resolved.routing == EndpointRouting()
    assert "openRouterRouting" not in resolved.adapter_compat
    assert "vercelGatewayRouting" not in resolved.adapter_compat


def test_resolve_request_ignores_direct_model_legacy_upstream_binding() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="openrouter",
        api="openai-completions",
        base_url="https://openrouter.ai/api/v1",
        compat=Compat.from_raw({THINKING_FORMAT: "openrouter"}),
    )
    registry = ModelRegistry.from_providers(
        {"openrouter": Provider(id="openrouter", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="openai/gpt-oss-120b_free",
        provider="openrouter",
        endpoint="openai-completions",
        compat={"upstreamModelId": "openai/gpt-oss-120b:free"},
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.upstream_model_id == "openai/gpt-oss-120b_free"
    assert "upstreamModelId" not in resolved.adapter_compat


def test_resolve_request_ignores_endpoint_legacy_upstream_binding() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="openrouter",
        api="openai-completions",
        base_url="https://openrouter.ai/api/v1",
        compat=Compat.from_raw(
            {
                "upstreamModelId": "openai/gpt-oss-120b:free",
                THINKING_FORMAT: "openrouter",
            }
        ),
        models={
            "openai/gpt-oss-120b_free": Model(
                id="openai/gpt-oss-120b_free",
                provider="openrouter",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"openrouter": Provider(id="openrouter", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model(
        "openrouter", "openai-completions", "openai/gpt-oss-120b_free"
    )

    resolved_endpoint = resolve_endpoint_for_model(model, registry=registry)
    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert "upstreamModelId" not in model.compat
    assert resolved_endpoint.upstream_model_id is None
    assert "upstreamModelId" not in resolved_endpoint.adapter_compat
    assert resolved.upstream_model_id == "openai/gpt-oss-120b_free"
    assert "upstreamModelId" not in resolved.adapter_compat


def test_resolve_request_uses_first_class_upstream_binding() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="openrouter",
        api="openai-completions",
        base_url="https://openrouter.ai/api/v1",
        compat=Compat.from_raw({THINKING_FORMAT: "openrouter"}),
    )
    registry = ModelRegistry.from_providers(
        {"openrouter": Provider(id="openrouter", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="openai/gpt-oss-120b_free",
        provider="openrouter",
        endpoint="openai-completions",
        upstream_id="openai/gpt-oss-120b:free",
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.upstream_model_id == "openai/gpt-oss-120b:free"
    assert "upstreamModelId" not in resolved.adapter_compat


def test_resolve_endpoint_ignores_direct_model_legacy_transport_routing() -> None:
    model = Model(
        id="dynamic",
        provider="openrouter",
        endpoint="openai-completions",
        compat={
            "providerTransport": "httpx",
            "openRouterRouting": {"only": ["anthropic"]},
            "vercelGatewayRouting": {"order": ["openai", "anthropic"]},
        },
    )

    resolved = resolve_endpoint_for_model(
        model,
        registry=ModelRegistry.from_providers({}),
    )

    assert resolved.transport == EndpointTransport()
    assert resolved.routing == EndpointRouting()
    assert "providerTransport" not in resolved.adapter_compat
    assert "openRouterRouting" not in resolved.adapter_compat
    assert "vercelGatewayRouting" not in resolved.adapter_compat


def test_resolve_request_merges_dynamic_model_transport_routing_with_endpoint() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        protocol=EndpointProtocolFeatures.from_raw(
            {
                "roles": {"developer": "unsupported"},
                "tools": {"strictSchema": "unsupported"},
            }
        ),
        dialect=EndpointWireDialect.from_raw(
            {"maxOutputTokensField": "max_completion_tokens"}
        ),
        transport=EndpointTransport(kind="httpx", stream="sse"),
        routing=EndpointRouting(
            request_overrides={
                "openrouter": {"only": ["endpoint"]},
                "vercelGateway": {"order": ["endpoint"]},
            }
        ),
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="dynamic",
        provider="custom",
        endpoint="openai-completions",
        transport=EndpointTransport(timeout=5),
        routing=EndpointRouting(request_overrides={"openrouter": {"order": ["model"]}}),
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.transport == EndpointTransport(
        kind="httpx",
        stream="sse",
        timeout=5,
    )
    assert resolved.routing == EndpointRouting(
        request_overrides={
            "openrouter": {"only": ["endpoint"], "order": ["model"]},
            "vercelGateway": {"order": ["endpoint"]},
        }
    )
    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["supportsStrictMode"] is False
    assert resolved.adapter_compat["maxTokensField"] == "max_completion_tokens"
    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved.dialect.max_output_tokens_field == "max_completion_tokens"


def test_resolve_request_preserves_direct_overrides_for_catalog_model_id() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        transport=EndpointTransport(kind="httpx", stream="sse"),
        routing=EndpointRouting(
            request_overrides={"openrouter": {"only": ["endpoint"]}}
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="model-a",
        provider="custom",
        endpoint="openai-completions",
        transport=EndpointTransport(timeout=5),
        routing=EndpointRouting(
            request_overrides={"openrouter": {"order": ["caller"]}}
        ),
        compat={"vercelGatewayRouting": {"order": ["openai", "anthropic"]}},
        capabilities=Capabilities(
            input=("text", "image"),
            context_window=8192,
            tool_use=True,
            reasoning=True,
        ),
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.transport == EndpointTransport(
        kind="httpx",
        stream="sse",
        timeout=5,
    )
    assert resolved.routing == EndpointRouting(
        request_overrides={
            "openrouter": {"only": ["endpoint"], "order": ["caller"]},
        }
    )
    assert resolved.capabilities == model.capabilities
    assert resolved.capabilities.context_window == 8192
    assert resolved.capabilities.supports_image_input is True


def test_resolve_request_preserves_direct_overrides_when_region_switches() -> None:
    cn_endpoint = Endpoint(
        id="openai-completions",
        provider="dashscope",
        api="openai-completions",
        base_url="https://cn.example/v1",
        region="cn",
        transport=EndpointTransport(kind="httpx", timeout=10),
        models={
            "qwen": Model(
                id="qwen",
                provider="dashscope",
                endpoint="openai-completions",
            )
        },
    )
    us_endpoint = Endpoint(
        id="openai-completions-us",
        provider="dashscope",
        api="openai-completions",
        base_url="https://us.example/v1",
        region="us",
        dialect=EndpointWireDialect.from_raw(
            {"maxOutputTokensField": "max_completion_tokens"}
        ),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["us"]}}),
        models={
            "qwen": Model(
                id="qwen",
                provider="dashscope",
                endpoint="openai-completions-us",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "dashscope": Provider(
                id="dashscope",
                endpoints={
                    cn_endpoint.id: cn_endpoint,
                    us_endpoint.id: us_endpoint,
                },
            )
        }
    )
    model = Model(
        id="qwen",
        provider="dashscope",
        endpoint="openai-completions",
        compat={"thinkingFormat": "caller"},
        defaults={"maxOutputTokens": 123},
        transport=EndpointTransport(timeout=5),
        routing=EndpointRouting(request_overrides={"openrouter": {"order": ["model"]}}),
        capabilities=Capabilities(context_window=8192, input=("text", "image")),
    )

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"LOUSHANG_REGION": "us"},
    )

    assert resolved.endpoint == "openai-completions-us"
    assert resolved.adapter_compat["maxTokensField"] == "max_completion_tokens"
    assert resolved.adapter_compat["thinkingFormat"] == "caller"
    assert resolved.max_tokens == 123
    assert resolved.transport == EndpointTransport(kind=None, timeout=5)
    assert resolved.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["us"], "order": ["model"]}}
    )
    assert resolved.capabilities.context_window == 8192
    assert resolved.capabilities.supports_image_input is True


def test_resolve_request_keeps_catalog_capabilities_without_direct_override() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
                capabilities=Capabilities(
                    context_window=4096,
                    tool_use=True,
                    reasoning=True,
                ),
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="model-a",
        provider="custom",
        endpoint="openai-completions",
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.capabilities.context_window == 4096
    assert resolved.capabilities.tool_use is True
    assert resolved.capabilities.reasoning is True


def test_resolve_request_accepts_unified_call_options() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://example.compat/v1",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        options=CallOptions(
            max_output_tokens=321,
            reasoning=ReasoningOptions(effort="high"),
            temperature=0.2,
        ),
        registry=registry,
        env={},
    )

    assert resolved.max_tokens == 321
    assert resolved.reasoning_effort == "high"
    assert resolved.temperature == 0.2


def test_resolve_request_applies_explicit_default_capability_override() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
                capabilities=Capabilities(
                    context_window=4096,
                    tool_use=True,
                    reasoning=True,
                ),
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="model-a",
        provider="custom",
        endpoint="openai-completions",
        capabilities=Capabilities(),
    ).with_contract_overrides(
        capabilities=Capabilities(),
    )

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.capabilities == Capabilities()
    assert resolved.capabilities.context_window is None
    assert resolved.capabilities.tool_use is False
    assert resolved.capabilities.reasoning is False


def test_with_contract_overrides_preserves_omitted_compat_override() -> None:
    model = Model(
        id="model-a",
        provider="custom",
        endpoint="openai-completions",
        compat={"supportsReasoningEffort": True},
    ).with_contract_overrides(capabilities=Capabilities())

    assert model.contract_compat["supportsReasoningEffort"] is True
    assert model.contract_capabilities == Capabilities()


def test_resolve_request_uses_bound_model_snapshot_when_registry_omitted() -> None:
    default_endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "supported"}}
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    custom_endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "unsupported"}}
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    default_registry = ModelRegistry.from_providers(
        {
            "custom": Provider(
                id="custom", endpoints={default_endpoint.id: default_endpoint}
            )
        }
    )
    custom_registry = ModelRegistry.from_providers(
        {
            "custom": Provider(
                id="custom", endpoints={custom_endpoint.id: custom_endpoint}
            )
        }
    )
    model = custom_registry.get_model("custom", "openai-completions", "model-a")
    previous_registry = get_default_model_registry()
    try:
        clear_default_model_registry()
        get_default_model_registry().replace_providers(default_registry.providers)

        resolved = resolve_request_for_model(model, env={})
    finally:
        clear_default_model_registry()
        get_default_model_registry().replace_providers(previous_registry.providers)

    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED


def test_resolve_request_uses_default_catalog_for_plain_api_hint() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://catalog.example/v1",
        auth=Auth(api_key_env="CUSTOM_API_KEY"),
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "unsupported"}}
        ),
        dialect=EndpointWireDialect.from_raw(
            {"maxOutputTokensField": "max_completion_tokens"}
        ),
        transport=EndpointTransport(kind="httpx", timeout=10),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
                capabilities=Capabilities(context_window=4096),
            )
        },
    )
    catalog = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="model-a",
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
    )
    previous_registry = get_default_model_registry()
    try:
        clear_default_model_registry()
        get_default_model_registry().replace_providers(catalog.providers)

        resolved = resolve_request_for_model(
            model,
            env={"CUSTOM_API_KEY": "secret"},
        )
        snapshot = resolve_model_endpoint(model)
    finally:
        clear_default_model_registry()
        get_default_model_registry().replace_providers(previous_registry.providers)

    assert snapshot is not None
    assert snapshot.base_url == "https://catalog.example/v1"
    assert resolved.base_url == "https://catalog.example/v1"
    assert resolved.headers["Authorization"] == "Bearer secret"
    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved.dialect.max_output_tokens_field == "max_completion_tokens"
    assert resolved.transport == EndpointTransport(kind="httpx", timeout=10)
    assert resolved.capabilities.context_window == 4096


def test_resolve_request_preserves_direct_api_endpoint_snapshot() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://catalog.example/v1",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    catalog = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = Model(
        id="model-a",
        provider="custom",
        endpoint="openai-completions",
        api="openai-completions",
        base_url="https://direct.example/v1",
    )
    previous_registry = get_default_model_registry()
    try:
        clear_default_model_registry()
        get_default_model_registry().replace_providers(catalog.providers)

        resolved = resolve_request_for_model(model, env={})
        snapshot = resolve_model_endpoint(model)
    finally:
        clear_default_model_registry()
        get_default_model_registry().replace_providers(previous_registry.providers)

    assert snapshot is not None
    assert snapshot.base_url == "https://direct.example/v1"
    assert resolved.base_url == "https://direct.example/v1"


def test_bound_endpoint_snapshot_keeps_endpoint_defaults_separate_from_request() -> (
    None
):
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        compat=Compat.from_raw({"supportsReasoningEffort": False}),
        defaults=Defaults.from_raw({"maxOutputTokens": 100}),
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "unsupported"}}
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
                compat={"supportsReasoningEffort": True},
                defaults={"maxOutputTokens": 200},
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    snapshot = resolve_model_endpoint(model)
    resolved_endpoint = resolve_endpoint_for_model(model)
    resolved_request = resolve_request_for_model(model, env={})

    assert snapshot is not None
    assert snapshot.compat["supportsReasoningEffort"] is False
    assert snapshot.defaults["maxOutputTokens"] == 100
    assert resolved_endpoint.adapter_compat["supportsReasoningEffort"] is False
    assert resolved_endpoint.defaults["maxOutputTokens"] == 100
    assert resolved_endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved_request.adapter_compat["supportsReasoningEffort"] is True
    assert resolved_request.defaults["maxOutputTokens"] == 200
    assert resolved_request.max_tokens == 200
    assert resolved_request.protocol.reasoning.effort is SupportStatus.SUPPORTED


def test_bound_endpoint_snapshot_keeps_endpoint_transport_routing_separate() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        transport=EndpointTransport(kind="httpx", timeout=10),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["base"]}}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
                transport=EndpointTransport(kind="sdk", timeout=20),
                routing=EndpointRouting(
                    request_overrides={"openrouter": {"only": ["model"]}}
                ),
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    snapshot = resolve_model_endpoint(model)
    resolved_endpoint = resolve_endpoint_for_model(model)
    resolved_request = resolve_request_for_model(model, env={})

    assert snapshot is not None
    assert snapshot.transport == EndpointTransport(kind="httpx", timeout=10)
    assert snapshot.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["base"]}}
    )
    assert resolved_endpoint.transport == EndpointTransport(kind="httpx", timeout=10)
    assert resolved_endpoint.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["base"]}}
    )
    assert resolved_request.transport == EndpointTransport(kind="sdk", timeout=20)
    assert resolved_request.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["model"]}}
    )


def test_resolve_request_preserves_bound_unknown_protocol_without_registry() -> None:
    clear_default_model_registry()
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        protocol=EndpointProtocolFeatures.from_raw({"roles": {"developer": "unknown"}}),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    snapshot = resolve_model_endpoint(model)
    resolved = resolve_request_for_model(model, env={})

    assert snapshot is not None
    assert snapshot.protocol.roles.developer is SupportStatus.UNKNOWN
    assert resolved.protocol.roles.developer is SupportStatus.UNKNOWN
    assert resolved.adapter_protocol.roles.developer is SupportStatus.UNSUPPORTED


def test_resolve_request_uses_base_url_env_override() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://static.example/v1",
        base_url_env="CUSTOM_BASE_URL",
        auth=Auth(api_key_env="CUSTOM_API_KEY"),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={
            "CUSTOM_BASE_URL": "https://env.example/v1",
            "CUSTOM_API_KEY": "secret",
        },
    )

    assert resolved.base_url == "https://env.example/v1"
    assert resolved.headers["Authorization"] == "Bearer secret"


def test_resolve_request_merges_options_headers_after_auth() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        auth=Auth(api_key_env="CUSTOM_API_KEY"),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"CUSTOM_API_KEY": "env-secret"},
        options=OpenAICompletionsOptions(
            headers={
                "Authorization": "Bearer explicit-secret",
                "X-Trace-Id": "trace-1",
            },
        ),
    )

    assert resolved.headers["Authorization"] == "Bearer explicit-secret"
    assert resolved.headers["X-Trace-Id"] == "trace-1"


def test_resolve_request_prefers_explicit_api_key_over_env() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        auth=Auth(api_key_env="CUSTOM_API_KEY", header="x-api-key", prefix=""),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"CUSTOM_API_KEY": "env-secret"},
        options=OpenAICompletionsOptions(api_key="explicit-secret"),
    )

    assert resolved.headers["x-api-key"] == "explicit-secret"
    assert "Authorization" not in resolved.headers


def test_resolve_request_uses_os_environ_for_base_url_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUSTOM_BASE_URL", "https://process-env.example/v1")
    endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://static.example/v1",
        base_url_env="CUSTOM_BASE_URL",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry)

    assert resolved.base_url == os.environ["CUSTOM_BASE_URL"]


def test_resolve_request_expands_base_url_env_template() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="cloudflare-workers-ai",
        api="openai-completions",
        base_url=(
            "https://api.cloudflare.com/client/v4/accounts/"
            "{CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        ),
        compat=Compat.from_raw(
            {
                SUPPORTS_STORE: False,
                SUPPORTS_DEVELOPER_ROLE: False,
                SUPPORTS_LONG_CACHE_RETENTION: False,
            }
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="cloudflare-workers-ai",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "cloudflare-workers-ai": Provider(
                id="cloudflare-workers-ai",
                endpoints={endpoint.id: endpoint},
            )
        }
    )
    model = registry.get_model("cloudflare-workers-ai", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"CLOUDFLARE_ACCOUNT_ID": "acct_123"},
    )

    assert (
        resolved.base_url
        == "https://api.cloudflare.com/client/v4/accounts/acct_123/ai/v1"
    )


def test_resolve_request_rejects_missing_base_url_env_template() -> None:
    endpoint = Endpoint(
        id="openai-completions",
        provider="cloudflare-workers-ai",
        api="openai-completions",
        base_url=(
            "https://api.cloudflare.com/client/v4/accounts/"
            "{CLOUDFLARE_ACCOUNT_ID}/ai/v1"
        ),
        models={
            "model-a": Model(
                id="model-a",
                provider="cloudflare-workers-ai",
                endpoint="openai-completions",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "cloudflare-workers-ai": Provider(
                id="cloudflare-workers-ai",
                endpoints={endpoint.id: endpoint},
            )
        }
    )
    model = registry.get_model("cloudflare-workers-ai", "openai-completions", "model-a")

    with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
        resolve_request_for_model(model, registry=registry, env={})


def test_resolve_request_uses_explicit_protocol_compat_bridge(tmp_path) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://api.openai.com/v1",
                                "protocol": {
                                    "store": "unsupported",
                                    "roles": {"developer": "unsupported"},
                                    "streaming": {
                                        "usage": "unsupported",
                                        "reasoningDelta": "supported",
                                    },
                                    "reasoning": {"effort": "supported"},
                                    "tools": {"strictSchema": "unsupported"},
                                    "cache": {"longRetention": "unsupported"},
                                    "session": {"affinityHeaders": "supported"},
                                },
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                            "toolUse": True,
                                            "reasoning": True,
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat["supportsStore"] is False
    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["supportsUsageInStreaming"] is False
    assert resolved.adapter_compat["supportsReasoningEffort"] is True
    assert resolved.adapter_compat["supportsStrictMode"] is False
    assert resolved.adapter_compat["supportsStreamReasoningDelta"] is True
    assert resolved.adapter_compat["supportsLongCacheRetention"] is False
    assert resolved.adapter_compat["sendSessionAffinityHeaders"] is True
    assert resolved.protocol.to_raw() == {
        "store": "unsupported",
        "roles": {"developer": "unsupported"},
        "streaming": {
            "usage": "unsupported",
            "reasoningDelta": "supported",
        },
        "reasoning": {"effort": "supported"},
        "tools": {"strictSchema": "unsupported"},
        "cache": {"longRetention": "unsupported"},
        "session": {"affinityHeaders": "supported"},
    }


def test_resolve_request_preserves_model_compat_override_over_endpoint_protocol(
    tmp_path,
) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://api.openai.com/v1",
                                "protocol": {
                                    "reasoning": {"effort": "unsupported"},
                                },
                                "models": {
                                    "model-a": {
                                        "compat": {"supportsReasoningEffort": True},
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                            "reasoning": True,
                                        },
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert model.compat["supportsReasoningEffort"] is True
    assert resolved.adapter_compat["supportsReasoningEffort"] is True
    assert resolved.protocol.to_raw()["reasoning"]["effort"] == "supported"


def test_resolve_request_uses_explicit_dialect_compat_bridge(tmp_path) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://api.openai.com/v1",
                                "dialect": {
                                    "maxOutputTokensField": "max_completion_tokens",
                                    "tools": {
                                        "resultNameRequired": True,
                                        "assistantBridgeRequired": True,
                                        "streamFlag": False,
                                    },
                                    "reasoning": {
                                        "wireFormat": "moonshot",
                                        "thinkingAsText": True,
                                        "assistantContentRequired": True,
                                    },
                                    "cache": {"controlFormat": "anthropic"},
                                },
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                            "toolUse": True,
                                            "reasoning": True,
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat["maxTokensField"] == "max_completion_tokens"
    assert resolved.adapter_compat["requiresToolResultName"] is True
    assert resolved.adapter_compat["requiresAssistantAfterToolResult"] is True
    assert resolved.adapter_compat["requiresThinkingAsText"] is True
    assert (
        resolved.adapter_compat["requiresReasoningContentOnAssistantMessages"] is True
    )
    assert resolved.adapter_compat["thinkingFormat"] == "moonshot"
    assert resolved.adapter_compat["zaiToolStream"] is False
    assert resolved.adapter_compat["cacheControlFormat"] == "anthropic"
    assert resolved.dialect.to_raw() == {
        "maxOutputTokensField": "max_completion_tokens",
        "tools": {
            "resultNameRequired": True,
            "assistantBridgeRequired": True,
            "streamFlag": False,
        },
        "reasoning": {
            "wireFormat": "moonshot",
            "thinkingAsText": True,
            "assistantContentRequired": True,
        },
        "cache": {"controlFormat": "anthropic"},
    }


def test_resolve_request_preserves_model_compat_override_over_endpoint_dialect(
    tmp_path,
) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://api.openai.com/v1",
                                "dialect": {
                                    "reasoning": {"wireFormat": "moonshot"},
                                },
                                "models": {
                                    "model-a": {
                                        "compat": {"thinkingFormat": "deepseek"},
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                            "reasoning": True,
                                        },
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert model.compat["thinkingFormat"] == "deepseek"
    assert resolved.adapter_compat["thinkingFormat"] == "deepseek"
    assert resolved.dialect.to_raw()["reasoning"]["wireFormat"] == "deepseek"


def test_resolve_request_preserves_openai_responses_protocol_bridge_keys(
    tmp_path,
) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-responses": {
                                "api": "openai-responses",
                                "baseUrl": "https://api.openai.com/v1",
                                "protocol": {
                                    "roles": {"developer": "unsupported"},
                                    "cache": {"longRetention": "unsupported"},
                                    "session": {"idHeader": "unsupported"},
                                },
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-responses", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["supportsLongCacheRetention"] is False
    assert resolved.adapter_compat["sendSessionIdHeader"] is False
    assert resolved.protocol.to_raw() == {
        "roles": {"developer": "unsupported"},
        "cache": {"longRetention": "unsupported"},
        "session": {"idHeader": "unsupported"},
    }


def test_resolve_request_treats_explicit_unknown_protocol_as_runtime_unsupported(
    tmp_path,
) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://api.openai.com/v1",
                                "protocol": {
                                    "store": "unknown",
                                    "roles": {"developer": "unknown"},
                                    "tools": {"strictSchema": "unknown"},
                                },
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                            "toolUse": True,
                                            "reasoning": True,
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    endpoint = registry.get_endpoint("custom", "openai-completions")
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert endpoint is not None
    assert endpoint.protocol.store is SupportStatus.UNKNOWN
    assert endpoint.protocol.roles.developer is SupportStatus.UNKNOWN
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNKNOWN
    assert resolved.adapter_compat["supportsStore"] is False
    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.adapter_compat["supportsStrictMode"] is False
    assert resolved.protocol.store is SupportStatus.UNKNOWN
    assert resolved.protocol.roles.developer is SupportStatus.UNKNOWN
    assert resolved.protocol.tools.strict_schema is SupportStatus.UNKNOWN


def test_resolve_request_model_compat_false_overrides_endpoint_unknown_protocol(
    tmp_path,
) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://api.openai.com/v1",
                                "protocol": {
                                    "roles": {"developer": "unknown"},
                                },
                                "models": {
                                    "model-a": {
                                        "compat": {
                                            "supportsDeveloperRole": False,
                                        },
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                        },
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat["supportsDeveloperRole"] is False
    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED


def test_resolve_request_preserves_anthropic_protocol_bridge_keys(tmp_path) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "anthropic-messages": {
                                "api": "anthropic-messages",
                                "baseUrl": "https://api.anthropic.com",
                                "protocol": {
                                    "reasoning": {"interleaved": "supported"},
                                    "tools": {
                                        "eagerInputStream": "unsupported",
                                        "fineGrained": "supported",
                                    },
                                    "cache": {
                                        "onTools": "unsupported",
                                        "longRetention": "unsupported",
                                    },
                                    "session": {"affinityHeaders": "supported"},
                                },
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                            "toolUse": True,
                                            "reasoning": True,
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "anthropic-messages", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.adapter_compat["supportsEagerToolInputStreaming"] is False
    assert resolved.adapter_compat["fineGrainedTools"] is True
    assert resolved.adapter_compat["interleavedThinking"] is True
    assert resolved.adapter_compat["supportsCacheControlOnTools"] is False
    assert resolved.adapter_compat["supportsLongCacheRetention"] is False
    assert resolved.adapter_compat["sendSessionAffinityHeaders"] is True
    assert resolved.protocol.to_raw() == {
        "reasoning": {"interleaved": "supported"},
        "tools": {
            "eagerInputStream": "unsupported",
            "fineGrained": "supported",
        },
        "cache": {
            "onTools": "unsupported",
            "longRetention": "unsupported",
        },
        "session": {"affinityHeaders": "supported"},
    }


def test_resolve_request_uses_legacy_transport_routing_as_typed_contract(
    tmp_path,
) -> None:
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": {
                                "api": "openai-completions",
                                "baseUrl": "https://gateway.example/v1",
                                "compat": {
                                    "providerTransport": "httpx",
                                    "openRouterRouting": {"only": ["anthropic"]},
                                    "vercelGatewayRouting": {
                                        "order": ["openai", "anthropic"]
                                    },
                                },
                                "models": {
                                    "model-a": {
                                        "capabilities": {
                                            "input": ["text"],
                                            "output": ["text"],
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(model, registry=registry, env={})

    assert resolved.transport.kind == "httpx"
    assert resolved.routing.request_overrides == {
        "openrouter": {"only": ["anthropic"]},
        "vercelGateway": {"order": ["openai", "anthropic"]},
    }
    assert "providerTransport" not in resolved.adapter_compat
    assert "openRouterRouting" not in resolved.adapter_compat
    assert "vercelGatewayRouting" not in resolved.adapter_compat


def test_resolve_request_selects_matching_region_endpoint() -> None:
    cn_endpoint = Endpoint(
        id="openai-completions",
        provider="dashscope",
        api="openai-completions",
        base_url="https://cn.example/v1",
        region="cn",
        auth=Auth(api_key_env="CN_API_KEY"),
        dialect=EndpointWireDialect.from_raw(
            {
                "maxOutputTokensField": "max_tokens",
                "reasoning": {"wireFormat": "deepseek"},
            }
        ),
        transport=EndpointTransport(kind="httpx", timeout=10),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["cn"]}}),
        models={
            "qwen": Model(
                id="qwen",
                provider="dashscope",
                endpoint="openai-completions",
            )
        },
    )
    us_endpoint = Endpoint(
        id="openai-completions-us",
        provider="dashscope",
        api="openai-completions",
        base_url="https://us.example/v1",
        region="us",
        auth=Auth(api_key_env="US_API_KEY"),
        dialect=EndpointWireDialect.from_raw(
            {
                "maxOutputTokensField": "max_completion_tokens",
                "reasoning": {"wireFormat": "moonshot"},
            }
        ),
        transport=EndpointTransport(kind="sdk", timeout=20),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["us"]}}),
        models={
            "qwen": Model(
                id="qwen", provider="dashscope", endpoint="openai-completions-us"
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "dashscope": Provider(
                id="dashscope",
                endpoints={
                    cn_endpoint.id: cn_endpoint,
                    us_endpoint.id: us_endpoint,
                },
            )
        }
    )
    model = registry.get_model("dashscope", "openai-completions", "qwen")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={
            "LOUSHANG_REGION": "us",
            "CN_API_KEY": "cn-secret",
            "US_API_KEY": "us-secret",
        },
    )

    assert resolved.endpoint == "openai-completions-us"
    assert resolved.region == "us"
    assert resolved.base_url == "https://us.example/v1"
    assert resolved.headers["Authorization"] == "Bearer us-secret"
    assert resolved.adapter_compat["maxTokensField"] == "max_completion_tokens"
    assert resolved.adapter_compat["thinkingFormat"] == "moonshot"
    assert resolved.transport == EndpointTransport(kind="sdk", timeout=20)
    assert resolved.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["us"]}}
    )


def test_resolve_request_selects_default_registry_region_for_bound_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cn_endpoint = Endpoint(
        id="openai-completions",
        provider="dashscope",
        api="openai-completions",
        base_url="https://cn.example/v1",
        region="cn",
        auth=Auth(api_key_env="CN_API_KEY"),
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "supported"}}
        ),
        dialect=EndpointWireDialect.from_raw({"maxOutputTokensField": "max_tokens"}),
        transport=EndpointTransport(timeout=10),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["cn"]}}),
        models={
            "qwen": Model(
                id="qwen",
                provider="dashscope",
                endpoint="openai-completions",
            )
        },
    )
    us_endpoint = Endpoint(
        id="openai-completions-us",
        provider="dashscope",
        api="openai-completions",
        base_url="https://us.example/v1",
        region="us",
        auth=Auth(api_key_env="US_API_KEY"),
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "unsupported"}}
        ),
        dialect=EndpointWireDialect.from_raw(
            {"maxOutputTokensField": "max_completion_tokens"}
        ),
        transport=EndpointTransport(kind="sdk", timeout=20),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["us"]}}),
        models={
            "qwen": Model(
                id="qwen", provider="dashscope", endpoint="openai-completions-us"
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "dashscope": Provider(
                id="dashscope",
                endpoints={
                    cn_endpoint.id: cn_endpoint,
                    us_endpoint.id: us_endpoint,
                },
            )
        }
    )
    monkeypatch.setattr(model_registry_module, "_default_model_registry", registry)
    model = registry.get_model("dashscope", "openai-completions", "qwen")

    resolved = resolve_request_for_model(
        model,
        env={
            "LOUSHANG_REGION": "us",
            "CN_API_KEY": "cn-secret",
            "US_API_KEY": "us-secret",
        },
    )

    assert resolved.endpoint == "openai-completions-us"
    assert resolved.region == "us"
    assert resolved.base_url == "https://us.example/v1"
    assert resolved.headers["Authorization"] == "Bearer us-secret"
    assert resolved.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert resolved.dialect.max_output_tokens_field == "max_completion_tokens"
    assert resolved.transport == EndpointTransport(kind="sdk", timeout=20)
    assert resolved.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["us"]}}
    )


def test_resolve_request_preserves_bound_contract_overrides_when_region_switches() -> (
    None
):
    cn_endpoint = Endpoint(
        id="openai-completions",
        provider="custom",
        api="openai-completions",
        base_url="https://cn.example/v1",
        region="cn",
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "unsupported"}}
        ),
        dialect=EndpointWireDialect.from_raw({"maxOutputTokensField": "max_tokens"}),
        transport=EndpointTransport(timeout=10),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["cn"]}}),
        models={
            "qwen": Model(
                id="qwen",
                provider="custom",
                endpoint="openai-completions",
            )
        },
    )
    us_endpoint = Endpoint(
        id="openai-completions-us",
        provider="custom",
        api="openai-completions",
        base_url="https://us.example/v1",
        region="us",
        protocol=EndpointProtocolFeatures.from_raw(
            {"roles": {"developer": "unsupported"}}
        ),
        dialect=EndpointWireDialect.from_raw(
            {"maxOutputTokensField": "max_completion_tokens"}
        ),
        transport=EndpointTransport(kind="sdk", timeout=20),
        routing=EndpointRouting(request_overrides={"openrouter": {"only": ["us"]}}),
        models={
            "qwen": Model(
                id="qwen",
                provider="custom",
                endpoint="openai-completions-us",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {
            "custom": Provider(
                id="custom",
                endpoints={
                    cn_endpoint.id: cn_endpoint,
                    us_endpoint.id: us_endpoint,
                },
            )
        }
    )
    model = registry.get_model("custom", "openai-completions", "qwen")
    model = model.with_contract_overrides(
        compat={
            "supportsDeveloperRole": True,
            "maxTokensField": "max_tokens",
        },
        capabilities=Capabilities(input=("text", "image"), reasoning=True),
    )

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"LOUSHANG_REGION": "us"},
    )

    assert resolved.endpoint == "openai-completions-us"
    assert resolved.protocol.roles.developer is SupportStatus.SUPPORTED
    assert resolved.dialect.max_output_tokens_field == "max_tokens"
    assert resolved.adapter_compat["supportsDeveloperRole"] is True
    assert resolved.adapter_compat["maxTokensField"] == "max_tokens"
    assert resolved.capabilities.supports_image_input is True
    assert resolved.capabilities.reasoning is True
    assert resolved.transport == EndpointTransport(kind="sdk", timeout=20)
    assert resolved.routing == EndpointRouting(
        request_overrides={"openrouter": {"only": ["us"]}}
    )


def test_resolve_request_reports_actual_region_when_region_falls_back() -> None:
    endpoint = Endpoint(
        id="openai-responses",
        provider="dashscope",
        api="openai-responses",
        base_url="https://cn.example/v1",
        region="cn",
        models={
            "qwen": Model(id="qwen", provider="dashscope", endpoint="openai-responses")
        },
    )
    registry = ModelRegistry.from_providers(
        {"dashscope": Provider(id="dashscope", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("dashscope", "openai-responses", "qwen")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"LOUSHANG_REGION": "missing"},
    )

    assert resolved.endpoint == "openai-responses"
    assert resolved.region == "cn"
    assert resolved.base_url == "https://cn.example/v1"


def test_bound_model_carries_endpoint_api_without_default_registry() -> None:
    clear_default_model_registry()
    endpoint = Endpoint(
        id="custom-endpoint",
        provider="custom",
        api="openai-completions",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="custom-endpoint",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "custom-endpoint", "model-a")

    assert resolve_model_api(model) == "openai-completions"


def test_bound_model_carries_endpoint_request_context_without_registry() -> None:
    clear_default_model_registry()
    endpoint = Endpoint(
        id="custom-endpoint",
        provider="custom",
        api="openai-completions",
        base_url="https://custom.example/v1",
        base_url_env="CUSTOM_BASE_URL",
        region="private",
        auth=Auth(api_key_env="CUSTOM_API_KEY"),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="custom-endpoint",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "custom-endpoint", "model-a")

    resolved = resolve_request_for_model(
        model,
        env={
            "CUSTOM_BASE_URL": "https://env-custom.example/v1",
            "CUSTOM_API_KEY": "secret",
        },
    )

    assert resolved.api == "openai-completions"
    assert resolved.base_url == "https://env-custom.example/v1"
    assert resolved.region == "private"
    assert resolved.headers["Authorization"] == "Bearer secret"


def test_list_models_returns_endpoint_bound_models_without_default_registry() -> None:
    clear_default_model_registry()
    endpoint = Endpoint(
        id="custom-endpoint",
        provider="custom",
        api="openai-completions",
        base_url_env="CUSTOM_BASE_URL",
        auth=Auth(api_key_env="CUSTOM_API_KEY"),
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="custom-endpoint",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.list_models(provider="custom")[0]

    resolved = resolve_request_for_model(
        model,
        env={
            "CUSTOM_BASE_URL": "https://env-custom.example/v1",
            "CUSTOM_API_KEY": "secret",
        },
    )

    assert resolve_model_api(model) == "openai-completions"
    assert resolved.base_url == "https://env-custom.example/v1"
    assert resolved.headers["Authorization"] == "Bearer secret"


def test_resolve_model_endpoint_returns_bound_snapshot_without_default_registry() -> (
    None
):
    clear_default_model_registry()
    endpoint = Endpoint(
        id="custom-endpoint",
        provider="custom",
        api="openai-completions",
        models={
            "model-a": Model(
                id="model-a",
                provider="custom",
                endpoint="custom-endpoint",
            )
        },
    )
    registry = ModelRegistry.from_providers(
        {"custom": Provider(id="custom", endpoints={endpoint.id: endpoint})}
    )
    model = registry.get_model("custom", "custom-endpoint", "model-a")

    snapshot = resolve_model_endpoint(model)
    assert snapshot is not None
    assert snapshot.id == "custom-endpoint"
    assert snapshot.provider_id == "custom"
    assert snapshot.api == "openai-completions"
    assert snapshot.get_model("model-a") == endpoint.get_model("model-a")
    assert resolve_model_endpoint(model, registry=registry) == endpoint


def test_loader_preserves_model_level_reasoning_defaults() -> None:
    registry = load_model_registry()
    model = registry.get_model(
        "dashscope",
        "openai-responses",
        "qwen3.7-plus",
    )

    assert model.compat["supportsReasoningEffort"] is True
    assert model.defaults["reasoningEffort"] == "medium"


def test_resolve_request_uses_model_endpoint_provider_auth_precedence(tmp_path) -> None:
    raw = {
        "providers": {
            "gateway": {
                "auth": {
                    "kind": "apiKey",
                    "apiKeyEnv": "PROVIDER_KEY",
                    "header": "Authorization",
                    "prefix": "Bearer ",
                    "extraHeaders": {"x-provider": "yes"},
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "auth": {
                            "apiKeyEnv": "ENDPOINT_KEY",
                            "header": "x-api-key",
                            "prefix": "",
                        },
                        "models": {
                            "model-a": {
                                "auth": {"apiKeyEnv": "MODEL_KEY"},
                                "capabilities": {"input": ["text"], "output": ["text"]},
                            }
                        },
                    }
                },
            }
        }
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    registry = load_model_registry_from_file(path)
    model = registry.get_model("gateway", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={
            "PROVIDER_KEY": "provider-secret",
            "ENDPOINT_KEY": "endpoint-secret",
            "MODEL_KEY": "model-secret",
        },
    )

    assert resolved.headers["x-api-key"] == "model-secret"
    assert "Authorization" not in resolved.headers
    assert resolved.headers["x-provider"] == "yes"


def test_resolve_request_merges_auth_extra_headers_with_child_override(
    tmp_path,
) -> None:
    raw = {
        "providers": {
            "gateway": {
                "auth": {
                    "apiKeyEnv": "GATEWAY_KEY",
                    "extraHeaders": {
                        "x-shared": "provider",
                        "x-provider-only": "yes",
                    },
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "auth": {
                            "extraHeaders": {
                                "x-shared": "endpoint",
                                "x-endpoint-only": "yes",
                            }
                        },
                        "models": {
                            "model-a": {
                                "auth": {
                                    "extraHeaders": {
                                        "x-shared": "model",
                                        "x-model-only": "yes",
                                    }
                                },
                                "capabilities": {"input": ["text"], "output": ["text"]},
                            }
                        },
                    }
                },
            }
        }
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    registry = load_model_registry_from_file(path)
    model = registry.get_model("gateway", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={"GATEWAY_KEY": "secret"},
    )

    assert resolved.headers["Authorization"] == "Bearer secret"
    assert resolved.headers["x-shared"] == "model"
    assert resolved.headers["x-provider-only"] == "yes"
    assert resolved.headers["x-endpoint-only"] == "yes"
    assert resolved.headers["x-model-only"] == "yes"


def test_resolve_request_uses_first_available_api_key_env_candidate(tmp_path) -> None:
    raw = {
        "providers": {
            "custom": {
                "auth": {
                    "apiKeyEnv": "FALLBACK_KEY",
                    "apiKeyEnvs": ["PRIMARY_KEY", "SECONDARY_KEY"],
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {"input": ["text"], "output": ["text"]}
                            }
                        },
                    }
                },
            }
        }
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={
            "PRIMARY_KEY": "",
            "SECONDARY_KEY": "secondary-secret",
            "FALLBACK_KEY": "fallback-secret",
        },
    )

    assert resolved.headers["Authorization"] == "Bearer secondary-secret"


def test_resolve_request_expands_extra_header_env_references(tmp_path) -> None:
    raw = {
        "providers": {
            "gateway": {
                "auth": {
                    "apiKeyEnv": "GATEWAY_KEY",
                    "extraHeaders": {
                        "x-tenant-id": "${LOUSHANG_TENANT_ID}",
                        "x-missing": "${MISSING_HEADER}",
                        "x-static": "static",
                    },
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {"input": ["text"], "output": ["text"]}
                            }
                        },
                    }
                },
            }
        }
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    registry = load_model_registry_from_file(path)
    model = registry.get_model("gateway", "openai-completions", "model-a")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={
            "GATEWAY_KEY": "secret",
            "LOUSHANG_TENANT_ID": "tenant-1",
        },
    )

    assert resolved.headers["Authorization"] == "Bearer secret"
    assert resolved.headers["x-tenant-id"] == "tenant-1"
    assert resolved.headers["x-static"] == "static"
    assert "x-missing" not in resolved.headers
