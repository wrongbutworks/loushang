from __future__ import annotations

import json
import os

import pytest

from loushang.ai.model import Auth, Endpoint, Model, ModelRegistry, Provider
from loushang.ai.model.loader import load_model_registry, load_model_registry_from_file
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


def test_resolve_request_merges_auth_extra_headers_with_child_override(tmp_path) -> None:
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
