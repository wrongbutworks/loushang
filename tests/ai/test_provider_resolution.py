from __future__ import annotations

import os

import pytest

from loushang.ai.model import Auth, Endpoint, Model, ModelRegistry, Provider
from loushang.ai.model.loader import load_model_registry
from loushang.ai.model.registry import clear_default_model_registry, resolve_model_api
from loushang.ai.options import OpenAICompletionsOptions
from loushang.ai.provider import resolve_request_for_model


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


def test_resolve_request_selects_matching_region_endpoint() -> None:
    cn_endpoint = Endpoint(
        id="openai-responses",
        provider="dashscope",
        api="openai-responses",
        base_url="https://cn.example/v1",
        region="cn",
        auth=Auth(api_key_env="CN_API_KEY"),
        models={
            "qwen": Model(id="qwen", provider="dashscope", endpoint="openai-responses")
        },
    )
    us_endpoint = Endpoint(
        id="openai-responses-us",
        provider="dashscope",
        api="openai-responses",
        base_url="https://us.example/v1",
        region="us",
        auth=Auth(api_key_env="US_API_KEY"),
        models={
            "qwen": Model(
                id="qwen", provider="dashscope", endpoint="openai-responses-us"
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
    model = registry.get_model("dashscope", "openai-responses", "qwen")

    resolved = resolve_request_for_model(
        model,
        registry=registry,
        env={
            "LOUSHANG_REGION": "us",
            "CN_API_KEY": "cn-secret",
            "US_API_KEY": "us-secret",
        },
    )

    assert resolved.endpoint == "openai-responses-us"
    assert resolved.region == "us"
    assert resolved.base_url == "https://us.example/v1"
    assert resolved.headers["Authorization"] == "Bearer us-secret"


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


def test_loader_preserves_model_level_reasoning_defaults() -> None:
    registry = load_model_registry()
    model = registry.get_model(
        "moonshot",
        "coding",
        "kimi-for-coding",
    )

    assert model.compat["supportsReasoningEffort"] is True
    assert model.defaults["reasoningEffort"] == "medium"
