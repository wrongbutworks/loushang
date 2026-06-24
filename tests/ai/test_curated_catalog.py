from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loushang.ai.model import (
    AnthropicMessagesConfig,
    ModelRegistry,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
    load_builtin_model_registry,
    load_model_registry_from_file,
)
from loushang.ai.model.loader import validate_model_registry_raw

REPO_ROOT = Path(__file__).resolve().parents[2]
CURATED_CATALOG_PATH = REPO_ROOT / "src/loushang/ai/model/models.json"


def _load_curated_raw() -> dict[str, Any]:
    return json.loads(CURATED_CATALOG_PATH.read_text(encoding="utf-8"))


def _load_curated_registry() -> ModelRegistry:
    return load_model_registry_from_file(CURATED_CATALOG_PATH)


def test_curated_catalog_loads_runtime_models_json() -> None:
    raw = _load_curated_raw()

    assert "schemaVersion" not in raw
    validate_model_registry_raw(raw)
    assert [provider.id for provider in _load_curated_registry().list_providers()] == [
        "anthropic",
        "baidu-qianfan",
        "dashscope",
        "deepseek",
        "minimax",
        "moonshot",
        "openai",
        "stepfun",
        "tencent-hunyuan",
        "volcano-ark",
        "zai",
    ]


def test_default_builtin_catalog_matches_curated_catalog() -> None:
    registry = load_builtin_model_registry()
    curated = _load_curated_registry()

    assert [provider.id for provider in registry.list_providers()] == [
        provider.id for provider in curated.list_providers()
    ]
    assert [
        (endpoint.provider_id, endpoint.id) for endpoint in registry.list_endpoints()
    ] == [(endpoint.provider_id, endpoint.id) for endpoint in curated.list_endpoints()]
    assert [
        (model.provider_id, model.endpoint_id, model.id)
        for model in registry.list_models()
    ] == [
        (model.provider_id, model.endpoint_id, model.id)
        for model in curated.list_models()
    ]


def test_curated_catalog_has_no_removed_model_contract_fields() -> None:
    raw = _load_curated_raw()
    removed_fields = {"compat", "protocol", "dialect"}

    for provider in raw["providers"].values():
        for endpoint in provider["endpoints"].values():
            assert removed_fields.isdisjoint(endpoint)
            for model in endpoint["models"].values():
                assert removed_fields.isdisjoint(model)


def test_curated_catalog_uses_core_adapter_configs() -> None:
    registry = _load_curated_registry()

    adapters = {
        (endpoint.provider_id, endpoint.id): type(endpoint.adapter)
        for endpoint in registry.list_endpoints()
    }

    assert adapters[("anthropic", "anthropic-messages")] is AnthropicMessagesConfig
    assert adapters[("openai", "openai-responses")] is OpenAIResponsesConfig
    assert adapters[("deepseek", "openai-completions")] is OpenAICompletionsConfig
    assert adapters[("moonshot", "openai-completions")] is OpenAICompletionsConfig


def test_minimax_anthropic_catalog_uses_sdk_base_url_and_short_cache() -> None:
    registry = _load_curated_registry()
    endpoint = registry.get_endpoint("minimax", "anthropic-messages")

    assert endpoint is not None
    assert endpoint.base_url == "https://api.minimax.io/anthropic"
    assert isinstance(endpoint.adapter, AnthropicMessagesConfig)
    assert endpoint.adapter.long_cache_retention is False


def test_curated_openai_style_custom_base_urls_declare_adapter() -> None:
    raw = _load_curated_raw()

    for provider_id, provider in raw["providers"].items():
        for endpoint_id, endpoint in provider["endpoints"].items():
            if provider_id == "openai" or endpoint["api"] != "openai-completions":
                continue
            if not (endpoint.get("baseUrl") or endpoint.get("baseUrlEnv")):
                continue
            assert endpoint.get("adapter"), (provider_id, endpoint_id)


def test_curated_catalog_keeps_key_model_defaults() -> None:
    registry = _load_curated_registry()
    kimi = registry.get_model("moonshot", "openai-completions", "kimi-k2.7-code")
    gpt = registry.get_model("openai", "openai-responses", "gpt-5.5")
    claude = registry.get_model("anthropic", "anthropic-messages", "claude-sonnet-4-6")

    assert kimi.defaults["maxOutputTokens"] == 32000
    assert kimi.defaults["reasoningEffort"] == "medium"
    assert gpt.capabilities.context_window == 1000000
    assert claude.pricing is not None
    assert claude.pricing.output == 15


def test_cli_catalog_commands_show_adapter(monkeypatch, capsys) -> None:
    from loushang.ai.cli.__main__ import main

    monkeypatch.setattr(
        "loushang.ai.cli.__main__.get_default_model_registry",
        load_builtin_model_registry,
    )

    main(["--json", "models", "show", "moonshot:openai-completions:kimi-k2.7-code"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "moonshot"
    assert payload["adapter"]["reasoningFormat"] == "moonshot"
    assert "compat" not in payload
