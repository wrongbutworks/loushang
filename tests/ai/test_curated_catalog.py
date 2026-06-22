from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loushang.ai.model import (
    ModelRegistry,
    SupportStatus,
    load_builtin_model_registry,
    load_model_registry_from_file,
)
from loushang.ai.model.loader import validate_model_registry_raw

REPO_ROOT = Path(__file__).resolve().parents[2]
CURATED_CATALOG_PATH = (
    REPO_ROOT / "src/loushang/ai/model/models.curated.v2.json"
)
EVIDENCE_DIR = REPO_ROOT / "docs/internals/architecture/ai/catalog-evidence"
EVIDENCE_TEMPLATE_PATH = EVIDENCE_DIR / "_template.md"
ANTHROPIC_EVIDENCE_PATH = EVIDENCE_DIR / "anthropic.md"
BAIDU_QIANFAN_EVIDENCE_PATH = EVIDENCE_DIR / "baidu-qianfan.md"
DASHSCOPE_EVIDENCE_PATH = EVIDENCE_DIR / "dashscope.md"
DEEPSEEK_EVIDENCE_PATH = EVIDENCE_DIR / "deepseek.md"
MINIMAX_EVIDENCE_PATH = EVIDENCE_DIR / "minimax.md"
MOONSHOT_EVIDENCE_PATH = EVIDENCE_DIR / "moonshot.md"
OPENAI_EVIDENCE_PATH = EVIDENCE_DIR / "openai.md"
TENCENT_HUNYUAN_EVIDENCE_PATH = EVIDENCE_DIR / "tencent-hunyuan.md"
VOLCANO_ARK_EVIDENCE_PATH = EVIDENCE_DIR / "volcano-ark.md"
ZAI_EVIDENCE_PATH = EVIDENCE_DIR / "zai.md"
CURATED_PROVIDER_MATRIX_PATH = (
    REPO_ROOT / "docs/internals/architecture/ai/curated-provider-matrix.md"
)

MAX_PROVIDERS = 11
MAX_ENDPOINTS = 16
MAX_MODELS = 20
MAX_MODELS_PER_PROVIDER = 2


def _load_curated_raw() -> dict[str, Any]:
    return json.loads(CURATED_CATALOG_PATH.read_text(encoding="utf-8"))


def _load_curated_registry() -> ModelRegistry:
    return load_model_registry_from_file(CURATED_CATALOG_PATH)


def test_curated_catalog_loads_v2_schema() -> None:
    raw = _load_curated_raw()

    assert raw["schemaVersion"] == 2
    validate_model_registry_raw(raw)
    assert [provider.id for provider in _load_curated_registry().list_providers()] == [
        "anthropic",
        "baidu-qianfan",
        "dashscope",
        "deepseek",
        "minimax",
        "moonshot",
        "openai",
        "tencent-hunyuan",
        "volcano-ark",
        "zai",
    ]


def test_default_builtin_catalog_still_uses_legacy_catalog() -> None:
    registry = load_builtin_model_registry()

    assert registry.list_providers()
    assert registry.get_provider("openai") is not None
    assert len(registry.list_models(provider="openai")) > len(
        _load_curated_registry().list_models(provider="openai")
    )
    assert len(registry.list_models(provider="anthropic")) > len(
        _load_curated_registry().list_models(provider="anthropic")
    )
    assert len(registry.list_models(provider="dashscope")) > len(
        _load_curated_registry().list_models(provider="dashscope")
    )
    assert len(registry.list_models(provider="baidu-qianfan")) > len(
        _load_curated_registry().list_models(provider="baidu-qianfan")
    )
    assert len(registry.list_models(provider="moonshot")) > len(
        _load_curated_registry().list_models(provider="moonshot")
    )
    assert len(registry.list_models(provider="minimax")) > len(
        _load_curated_registry().list_models(provider="minimax")
    )
    assert len(registry.list_models(provider="tencent-hunyuan")) > len(
        _load_curated_registry().list_models(provider="tencent-hunyuan")
    )
    assert len(registry.list_models(provider="volcano-ark")) > len(
        _load_curated_registry().list_models(provider="volcano-ark")
    )
    assert len(registry.list_models(provider="zai")) > len(
        _load_curated_registry().list_models(provider="zai")
    )


def test_curated_catalog_includes_verified_anthropic_messages_models() -> None:
    registry = _load_curated_registry()

    provider = registry.get_provider("anthropic")
    assert provider is not None
    assert provider.name == "Anthropic"
    assert provider.website == "https://docs.anthropic.com"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "ANTHROPIC_API_KEY"
    assert provider.auth.header == "x-api-key"
    assert provider.auth.prefix == ""
    assert provider.auth.extra_headers == {"anthropic-version": "2023-06-01"}

    endpoint = registry.get_endpoint("anthropic", "anthropic-messages")
    assert endpoint is not None
    assert endpoint.api == "anthropic-messages"
    assert endpoint.base_url == "https://api.anthropic.com"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "ANTHROPIC_API_KEY"
    assert endpoint.auth.extra_headers == {"anthropic-version": "2023-06-01"}
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.interleaved is SupportStatus.SUPPORTED
    assert endpoint.protocol.tools.fine_grained is SupportStatus.SUPPORTED
    assert endpoint.protocol.cache.long_retention is SupportStatus.SUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.reasoning.wire_format == "anthropic"
    assert endpoint.dialect.reasoning.thinking_as_text is False
    assert endpoint.dialect.cache.control_format == "anthropic"

    models = registry.list_models(provider="anthropic")
    assert [model.id for model in models] == [
        "claude-opus-4-8",
        "claude-sonnet-4-6",
    ]

    opus = registry.get_model("anthropic", "anthropic-messages", "claude-opus-4-8")
    assert opus is not None
    assert opus.name == "Claude Opus 4.8"
    assert opus.context_window == 1_000_000
    assert opus.max_tokens == 128_000
    assert opus.capabilities.input == ("text", "image")
    assert opus.capabilities.output == ("text",)
    assert opus.reasoning is True
    assert opus.supports_stream is True
    assert opus.supports_tool_use is True
    assert opus.supports_structured_output is True
    assert opus.supports_attachment is False
    assert opus.supports_temperature is False
    assert opus.pricing is not None
    assert opus.pricing.input == 5
    assert opus.pricing.output == 25
    assert opus.pricing.cache_read == 0.5
    assert opus.pricing.cache_write == 6.25

    sonnet = registry.get_model(
        "anthropic", "anthropic-messages", "claude-sonnet-4-6"
    )
    assert sonnet is not None
    assert sonnet.name == "Claude Sonnet 4.6"
    assert sonnet.context_window == 1_000_000
    assert sonnet.max_tokens == 64_000
    assert sonnet.supports_temperature is True
    assert sonnet.pricing is not None
    assert sonnet.pricing.input == 3
    assert sonnet.pricing.output == 15
    assert sonnet.pricing.cache_read == 0.3
    assert sonnet.pricing.cache_write == 3.75


def test_curated_catalog_includes_verified_baidu_qianfan_ernie_model() -> None:
    registry = _load_curated_registry()

    curated_model_ids = {
        model.id for model in registry.list_models(provider="baidu-qianfan")
    }
    assert "ernie-5.0" not in curated_model_ids
    assert "deepseek-v3.2" not in curated_model_ids

    provider = registry.get_provider("baidu-qianfan")
    assert provider is not None
    assert provider.name == "Baidu Qianfan"
    assert provider.website == "https://cloud.baidu.com/product/qianfan"
    assert provider.auth is not None
    assert provider.auth.api_key_env is None
    assert provider.auth.api_key_envs == (
        "QIANFAN_API_KEY",
        "BAIDU_QIANFAN_API_KEY",
    )
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("baidu-qianfan", "openai-completions-cn")
    assert endpoint is not None
    assert endpoint.api == "openai-completions"
    assert endpoint.base_url == "https://qianfan.baidubce.com/v2"
    assert endpoint.region == "cn"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env is None
    assert endpoint.auth.api_key_envs == (
        "QIANFAN_API_KEY",
        "BAIDU_QIANFAN_API_KEY",
    )
    assert endpoint.protocol.store is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.tools.assistant_bridge_required is False
    assert endpoint.dialect.tools.result_name_required is False
    assert endpoint.dialect.tools.stream_flag is False
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="baidu-qianfan")
    assert [model.id for model in models] == ["ernie-5.1"]

    model = registry.get_model(
        "baidu-qianfan",
        "openai-completions-cn",
        "ernie-5.1",
    )
    assert model is not None
    assert model.name == "ERNIE 5.1"
    assert model.alias == "default-chat"
    assert model.last_updated == "2026-05-08"
    assert model.context_window == 248_832
    assert model.max_tokens == 65_536
    assert model.defaults.get("maxOutputTokens") == 4_096
    assert model.capabilities.input == ("text",)
    assert model.capabilities.output == ("text",)
    assert model.reasoning is True
    assert model.supports_stream is True
    assert model.supports_tool_use is True
    assert model.supports_structured_output is True
    assert model.supports_attachment is False
    assert model.supports_temperature is True
    assert model.pricing is not None
    assert model.pricing.currency == "CNY"
    assert model.pricing.input == 6
    assert model.pricing.output == 22
    assert model.pricing.cache_read is None
    assert model.pricing.cache_write is None


def test_curated_catalog_includes_verified_dashscope_responses_models() -> None:
    registry = _load_curated_registry()

    assert registry.get_endpoint("dashscope", "openai-responses-sg") is None
    assert registry.get_endpoint("dashscope", "openai-responses-us") is None

    provider = registry.get_provider("dashscope")
    assert provider is not None
    assert provider.name == "Alibaba Cloud DashScope"
    assert provider.website == "https://dashscope.aliyun.com"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "DASHSCOPE_API_KEY"
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("dashscope", "openai-responses")
    assert endpoint is not None
    assert endpoint.api == "openai-responses"
    assert endpoint.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert endpoint.region == "cn"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "DASHSCOPE_API_KEY"
    assert endpoint.protocol.roles.developer is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort_map == {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "max",
    }
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.cache.prompt_key is SupportStatus.SUPPORTED
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="dashscope")
    assert [model.id for model in models] == ["qwen3.7-max", "qwen3.7-plus"]

    max_model = registry.get_model("dashscope", "openai-responses", "qwen3.7-max")
    assert max_model is not None
    assert max_model.name == "Qwen3.7 Max"
    assert max_model.alias == "qwen-main"
    assert max_model.context_window == 1_000_000
    assert max_model.max_tokens is None
    assert max_model.defaults.get("maxOutputTokens") == 32_000
    assert max_model.defaults.get("reasoningEffort") == "medium"
    assert max_model.capabilities.input == ("text", "image")
    assert max_model.capabilities.output == ("text",)
    assert max_model.reasoning is True
    assert max_model.supports_stream is True
    assert max_model.supports_tool_use is True
    assert max_model.supports_structured_output is True
    assert max_model.supports_attachment is False
    assert max_model.supports_temperature is True
    assert max_model.pricing is not None
    assert max_model.pricing.currency == "CNY"
    assert max_model.pricing.input == 12
    assert max_model.pricing.output == 36
    assert max_model.pricing.cache_read is None
    assert max_model.pricing.cache_write is None

    plus = registry.get_model("dashscope", "openai-responses", "qwen3.7-plus")
    assert plus is not None
    assert plus.name == "Qwen3.7 Plus"
    assert plus.alias == "qwen-balanced"
    assert plus.context_window == 1_000_000
    assert plus.max_tokens is None
    assert plus.defaults.get("maxOutputTokens") == 32_000
    assert plus.defaults.get("reasoningEffort") == "medium"
    assert plus.reasoning is True
    assert plus.supports_temperature is True
    assert plus.pricing is not None
    assert plus.pricing.currency == "CNY"
    assert plus.pricing.input == 2
    assert plus.pricing.output == 8
    assert plus.pricing.cache_read is None
    assert plus.pricing.cache_write is None


def test_curated_catalog_includes_verified_deepseek_v4_models() -> None:
    registry = _load_curated_registry()

    curated_model_ids = {model.id for model in registry.list_models(provider="deepseek")}
    assert "deepseek-r1" not in curated_model_ids
    assert "deepseek-v3.2" not in curated_model_ids

    provider = registry.get_provider("deepseek")
    assert provider is not None
    assert provider.name == "DeepSeek"
    assert provider.website == "https://api-docs.deepseek.com"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "DEEPSEEK_API_KEY"
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("deepseek", "openai-completions")
    assert endpoint is not None
    assert endpoint.api == "openai-completions"
    assert endpoint.base_url == "https://api.deepseek.com"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "DEEPSEEK_API_KEY"
    assert endpoint.protocol.store is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort_map == {
        "low": "high",
        "medium": "high",
        "high": "high",
        "xhigh": "max",
    }
    assert endpoint.protocol.tools.strict_schema is SupportStatus.SUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.tools.assistant_bridge_required is False
    assert endpoint.dialect.tools.result_name_required is False
    assert endpoint.dialect.tools.stream_flag is False
    assert endpoint.dialect.reasoning.wire_format == "deepseek"
    assert endpoint.dialect.reasoning.thinking_as_text is False
    assert endpoint.dialect.reasoning.assistant_content_required is True
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="deepseek")
    assert [model.id for model in models] == ["deepseek-v4-flash", "deepseek-v4-pro"]

    flash = registry.get_model("deepseek", "openai-completions", "deepseek-v4-flash")
    assert flash is not None
    assert flash.name == "DeepSeek V4 Flash"
    assert flash.alias == "fast-chat"
    assert flash.context_window == 1_000_000
    assert flash.max_tokens == 384_000
    assert flash.capabilities.input == ("text",)
    assert flash.capabilities.output == ("text",)
    assert flash.reasoning is True
    assert flash.supports_stream is True
    assert flash.supports_tool_use is True
    assert flash.supports_structured_output is True
    assert flash.supports_attachment is False
    assert flash.supports_temperature is True
    assert flash.pricing is not None
    assert flash.pricing.currency == "USD"
    assert flash.pricing.input == 0.14
    assert flash.pricing.output == 0.28
    assert flash.pricing.cache_read == 0.0028
    assert flash.pricing.cache_write is None

    pro = registry.get_model("deepseek", "openai-completions", "deepseek-v4-pro")
    assert pro is not None
    assert pro.name == "DeepSeek V4 Pro"
    assert pro.alias == "default-chat"
    assert pro.context_window == 1_000_000
    assert pro.max_tokens == 384_000
    assert pro.reasoning is True
    assert pro.supports_temperature is True
    assert pro.pricing is not None
    assert pro.pricing.currency == "USD"
    assert pro.pricing.input == 0.435
    assert pro.pricing.output == 0.87
    assert pro.pricing.cache_read == 0.003625
    assert pro.pricing.cache_write is None


def test_curated_catalog_includes_verified_minimax_m3_model() -> None:
    registry = _load_curated_registry()

    assert registry.get_provider("minimax-cn") is None

    provider = registry.get_provider("minimax")
    assert provider is not None
    assert provider.name == "MiniMax"
    assert provider.website == "https://platform.minimax.io"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "MINIMAX_API_KEY"
    assert provider.auth.header == "x-api-key"
    assert provider.auth.prefix == ""

    endpoint = registry.get_endpoint("minimax", "anthropic-messages")
    assert endpoint is not None
    assert endpoint.api == "anthropic-messages"
    assert endpoint.base_url == "https://api.minimax.io/anthropic/v1"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "MINIMAX_API_KEY"
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.reasoning.wire_format == "anthropic"
    assert endpoint.dialect.reasoning.thinking_as_text is False
    assert endpoint.dialect.reasoning.assistant_content_required is False
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="minimax")
    assert [model.id for model in models] == ["MiniMax-M3"]

    model = registry.get_model("minimax", "anthropic-messages", "MiniMax-M3")
    assert model is not None
    assert model.name == "MiniMax-M3"
    assert model.alias == "default-chat"
    assert model.context_window == 1_000_000
    assert model.max_tokens is None
    assert model.capabilities.input == ("text", "image")
    assert model.capabilities.output == ("text",)
    assert model.reasoning is True
    assert model.supports_stream is True
    assert model.supports_tool_use is True
    assert model.supports_structured_output is True
    assert model.supports_attachment is False
    assert model.supports_temperature is True
    assert model.pricing is not None
    assert model.pricing.currency == "USD"
    assert model.pricing.input == 0.6
    assert model.pricing.output == 2.4
    assert model.pricing.cache_read == 0.12
    assert model.pricing.cache_write is None


def test_curated_catalog_includes_verified_moonshot_openai_compatible_models() -> None:
    registry = _load_curated_registry()

    assert registry.get_provider("moonshotai") is None
    assert registry.get_provider("moonshotai-cn") is None
    assert registry.get_provider("kimi-coding") is None

    provider = registry.get_provider("moonshot")
    assert provider is not None
    assert provider.name == "Moonshot AI"
    assert provider.website == "https://platform.kimi.ai"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "MOONSHOT_API_KEY"
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("moonshot", "openai-completions")
    assert endpoint is not None
    assert endpoint.api == "openai-completions"
    assert endpoint.base_url == "https://api.moonshot.ai/v1"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "MOONSHOT_API_KEY"
    assert endpoint.protocol.store is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.reasoning.wire_format == "moonshot"
    assert endpoint.dialect.reasoning.thinking_as_text is False

    models = registry.list_models(provider="moonshot")
    assert [model.id for model in models] == ["kimi-k2.6", "kimi-k2.7-code"]

    general = registry.get_model("moonshot", "openai-completions", "kimi-k2.6")
    assert general is not None
    assert general.name == "Kimi K2.6"
    assert general.alias == "default-chat"
    assert general.context_window == 262_144
    assert general.max_tokens is None
    assert general.defaults.get("maxOutputTokens") == 32_000
    assert general.capabilities.input == ("text", "image")
    assert general.capabilities.output == ("text",)
    assert general.reasoning is True
    assert general.supports_stream is True
    assert general.supports_tool_use is True
    assert general.supports_structured_output is True
    assert general.supports_attachment is False
    assert general.supports_temperature is True
    assert general.pricing is not None
    assert general.pricing.currency == "USD"
    assert general.pricing.input == 0.95
    assert general.pricing.output == 4
    assert general.pricing.cache_read == 0.16
    assert general.pricing.cache_write is None

    coding = registry.get_model("moonshot", "openai-completions", "kimi-k2.7-code")
    assert coding is not None
    assert coding.name == "Kimi K2.7 Code"
    assert coding.alias == "default-coding"
    assert coding.context_window == 262_144
    assert coding.max_tokens is None
    assert coding.defaults.get("maxOutputTokens") == 32_000
    assert coding.reasoning is True
    assert coding.supports_temperature is False
    assert coding.pricing is not None
    assert coding.pricing.input == 0.95
    assert coding.pricing.output == 4
    assert coding.pricing.cache_read == 0.19
    assert coding.pricing.cache_write is None


def test_curated_catalog_includes_verified_tencent_hunyuan_model() -> None:
    registry = _load_curated_registry()

    curated_model_ids = {
        model.id for model in registry.list_models(provider="tencent-hunyuan")
    }
    assert "hunyuan-2.0-instruct-20251111" not in curated_model_ids
    assert "hunyuan-vision-1.5-instruct" not in curated_model_ids

    provider = registry.get_provider("tencent-hunyuan")
    assert provider is not None
    assert provider.name == "Tencent Hunyuan"
    assert provider.website == "https://cloud.tencent.com/product/hunyuan"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "HUNYUAN_API_KEY"
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("tencent-hunyuan", "openai-completions")
    assert endpoint is not None
    assert endpoint.api == "openai-completions"
    assert endpoint.base_url == "https://api.hunyuan.cloud.tencent.com/v1"
    assert endpoint.region == "cn"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "HUNYUAN_API_KEY"
    assert endpoint.protocol.store is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.tools.assistant_bridge_required is False
    assert endpoint.dialect.tools.result_name_required is False
    assert endpoint.dialect.tools.stream_flag is False
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="tencent-hunyuan")
    assert [model.id for model in models] == ["hunyuan-turbos-latest"]

    model = registry.get_model(
        "tencent-hunyuan",
        "openai-completions",
        "hunyuan-turbos-latest",
    )
    assert model is not None
    assert model.name == "Hunyuan TurboS Latest"
    assert model.alias == "default-chat"
    assert model.last_updated == "2025-07-16"
    assert model.context_window == 32_768
    assert model.max_tokens == 16_384
    assert model.defaults.get("maxOutputTokens") == 4_096
    assert model.capabilities.input == ("text",)
    assert model.capabilities.output == ("text",)
    assert model.reasoning is False
    assert model.supports_stream is True
    assert model.supports_tool_use is True
    assert model.supports_structured_output is False
    assert model.supports_attachment is False
    assert model.supports_temperature is True
    assert model.pricing is not None
    assert model.pricing.currency == "CNY"
    assert model.pricing.input == 0.8
    assert model.pricing.output == 2
    assert model.pricing.cache_read is None
    assert model.pricing.cache_write is None


def test_curated_catalog_includes_verified_volcano_ark_doubao_model() -> None:
    registry = _load_curated_registry()

    provider = registry.get_provider("volcano-ark")
    assert provider is not None
    assert provider.name == "Volcano Ark"
    assert provider.website == "https://www.volcengine.com/product/ark"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "ARK_API_KEY"
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("volcano-ark", "openai-completions-cn-beijing")
    assert endpoint is not None
    assert endpoint.api == "openai-completions"
    assert endpoint.base_url == "https://ark.cn-beijing.volces.com/api/v3"
    assert endpoint.region == "cn-beijing"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "ARK_API_KEY"
    assert endpoint.protocol.store is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.tools.assistant_bridge_required is False
    assert endpoint.dialect.tools.result_name_required is False
    assert endpoint.dialect.tools.stream_flag is False
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="volcano-ark")
    assert [model.id for model in models] == ["doubao-seed-2-0-lite-260215"]

    model = registry.get_model(
        "volcano-ark",
        "openai-completions-cn-beijing",
        "doubao-seed-2-0-lite-260215",
    )
    assert model is not None
    assert model.name == "Doubao Seed 2.0 Lite"
    assert model.alias == "default-chat"
    assert model.last_updated == "2026-02-15"
    assert model.context_window == 262_144
    assert model.max_tokens is None
    assert model.capabilities.input == ("text", "image")
    assert model.capabilities.output == ("text",)
    assert model.reasoning is False
    assert model.supports_stream is True
    assert model.supports_tool_use is True
    assert model.supports_structured_output is True
    assert model.supports_attachment is False
    assert model.supports_temperature is True
    assert model.pricing is None


def test_curated_catalog_includes_verified_zai_glm_models() -> None:
    registry = _load_curated_registry()

    assert registry.get_provider("zai-coding-cn") is None

    provider = registry.get_provider("zai")
    assert provider is not None
    assert provider.name == "Z.AI"
    assert provider.website == "https://docs.z.ai"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "ZAI_API_KEY"
    assert provider.auth.header == "Authorization"
    assert provider.auth.prefix == "Bearer "

    endpoint = registry.get_endpoint("zai", "openai-completions")
    assert endpoint is not None
    assert endpoint.api == "openai-completions"
    assert endpoint.base_url == "https://api.z.ai/api/paas/v4/"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "ZAI_API_KEY"
    assert endpoint.protocol.store is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.UNSUPPORTED
    assert endpoint.protocol.tools.strict_schema is SupportStatus.UNSUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_tokens"
    assert endpoint.dialect.tools.assistant_bridge_required is False
    assert endpoint.dialect.tools.result_name_required is False
    assert endpoint.dialect.tools.stream_flag is False
    assert endpoint.dialect.reasoning.wire_format == "zai-thinking"
    assert endpoint.dialect.reasoning.thinking_as_text is False
    assert endpoint.dialect.reasoning.assistant_content_required is False
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="zai")
    assert [model.id for model in models] == ["glm-5.1", "glm-5.2"]

    flagship = registry.get_model("zai", "openai-completions", "glm-5.2")
    assert flagship is not None
    assert flagship.name == "GLM-5.2"
    assert flagship.alias == "default-chat"
    assert flagship.context_window == 1_000_000
    assert flagship.max_tokens == 131_072
    assert flagship.defaults.get("maxOutputTokens") == 4_096
    assert flagship.capabilities.input == ("text",)
    assert flagship.capabilities.output == ("text",)
    assert flagship.reasoning is True
    assert flagship.supports_stream is True
    assert flagship.supports_tool_use is True
    assert flagship.supports_structured_output is True
    assert flagship.supports_attachment is False
    assert flagship.supports_temperature is True
    assert flagship.pricing is not None
    assert flagship.pricing.currency == "USD"
    assert flagship.pricing.input == 1.4
    assert flagship.pricing.output == 4.4
    assert flagship.pricing.cache_read == 0.26
    assert flagship.pricing.cache_write is None

    balanced = registry.get_model("zai", "openai-completions", "glm-5.1")
    assert balanced is not None
    assert balanced.name == "GLM-5.1"
    assert balanced.alias == "balanced-chat"
    assert balanced.context_window == 200_000
    assert balanced.max_tokens == 131_072
    assert balanced.defaults.get("maxOutputTokens") == 4_096
    assert balanced.reasoning is True
    assert balanced.supports_stream is True
    assert balanced.supports_tool_use is True
    assert balanced.supports_structured_output is True
    assert balanced.supports_attachment is False
    assert balanced.supports_temperature is True
    assert balanced.pricing is not None
    assert balanced.pricing.currency == "USD"
    assert balanced.pricing.input == 1.4
    assert balanced.pricing.output == 4.4
    assert balanced.pricing.cache_read == 0.26
    assert balanced.pricing.cache_write is None


def test_curated_catalog_includes_verified_openai_responses_models() -> None:
    registry = _load_curated_registry()

    provider = registry.get_provider("openai")
    assert provider is not None
    assert provider.name == "OpenAI"
    assert provider.website == "https://platform.openai.com"
    assert provider.auth is not None
    assert provider.auth.api_key_env == "OPENAI_API_KEY"

    endpoint = registry.get_endpoint("openai", "openai-responses")
    assert endpoint is not None
    assert endpoint.api == "openai-responses"
    assert endpoint.base_url == "https://api.openai.com/v1"
    assert endpoint.preferred is True
    assert endpoint.auth is not None
    assert endpoint.auth.api_key_env == "OPENAI_API_KEY"
    assert endpoint.protocol.store is SupportStatus.SUPPORTED
    assert endpoint.protocol.roles.developer is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.usage is SupportStatus.SUPPORTED
    assert endpoint.protocol.streaming.reasoning_delta is SupportStatus.SUPPORTED
    assert endpoint.protocol.reasoning.effort is SupportStatus.SUPPORTED
    assert endpoint.protocol.tools.strict_schema is SupportStatus.SUPPORTED
    assert endpoint.dialect.max_output_tokens_field == "max_output_tokens"
    assert endpoint.transport.kind == "http"
    assert endpoint.transport.stream == "sse"

    models = registry.list_models(provider="openai")
    assert [model.id for model in models] == ["gpt-5.4-mini", "gpt-5.5"]

    flagship = registry.get_model("openai", "openai-responses", "gpt-5.5")
    assert flagship is not None
    assert flagship.name == "GPT-5.5"
    assert flagship.knowledge == "2025-12-01"
    assert flagship.context_window == 1_000_000
    assert flagship.max_tokens == 128_000
    assert flagship.capabilities.input == ("text", "image")
    assert flagship.capabilities.output == ("text",)
    assert flagship.reasoning is True
    assert flagship.supports_stream is True
    assert flagship.supports_tool_use is True
    assert flagship.supports_structured_output is True
    assert flagship.pricing is not None
    assert flagship.pricing.input == 5
    assert flagship.pricing.output == 30
    assert flagship.pricing.cache_read == 0.5
    assert flagship.pricing.cache_write is None

    mini = registry.get_model("openai", "openai-responses", "gpt-5.4-mini")
    assert mini is not None
    assert mini.name == "GPT-5.4 mini"
    assert mini.knowledge == "2025-08-31"
    assert mini.context_window == 400_000
    assert mini.max_tokens == 128_000
    assert mini.pricing is not None
    assert mini.pricing.input == 0.75
    assert mini.pricing.output == 4.5
    assert mini.pricing.cache_read == 0.075
    assert mini.pricing.cache_write is None


def test_curated_catalog_budget_limits() -> None:
    registry = _load_curated_registry()
    providers = registry.list_providers()
    endpoints = registry.list_endpoints()
    models = registry.list_models()

    assert len(providers) <= MAX_PROVIDERS
    assert len(endpoints) <= MAX_ENDPOINTS
    assert len(models) <= MAX_MODELS
    for provider in providers:
        assert (
            len(registry.list_models(provider=provider.id)) <= MAX_MODELS_PER_PROVIDER
        )


def test_curated_catalog_has_no_legacy_compat_keys() -> None:
    offenders: list[str] = []

    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, entry in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                if key == "compat":
                    offenders.append(next_path)
                walk(entry, next_path)
        elif isinstance(value, list):
            for index, entry in enumerate(value):
                walk(entry, f"{path}[{index}]")

    walk(_load_curated_raw(), "")

    assert offenders == []


def test_curated_catalog_has_at_most_one_preferred_endpoint_per_model() -> None:
    registry = _load_curated_registry()

    for provider in registry.list_providers():
        preferred_by_model: dict[str, list[str]] = {}
        for endpoint in registry.list_endpoints(provider=provider.id):
            if not endpoint.preferred:
                continue
            for model_id in endpoint.models:
                preferred_by_model.setdefault(model_id, []).append(endpoint.id)

        assert {
            model_id: endpoint_ids
            for model_id, endpoint_ids in preferred_by_model.items()
            if len(endpoint_ids) > 1
        } == {}


def test_catalog_evidence_template_matches_required_sections() -> None:
    text = EVIDENCE_TEMPLATE_PATH.read_text(encoding="utf-8")

    for section in [
        "# Provider evidence: <provider>",
        "- Verified at: YYYY-MM-DD",
        "- Issue: #...",
        "- Official docs:",
        "- Authentication:",
        "- Endpoint:",
        "- Included models:",
        "- Verified capabilities:",
        "- Unknown/omitted facts:",
        "- Contract tests:",
        "- Manual live smoke:",
    ]:
        assert section in text


def test_anthropic_evidence_matches_curated_provider_fixture() -> None:
    text = ANTHROPIC_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: anthropic",
        "- Verified at: 2026-06-22",
        "https://docs.anthropic.com/en/docs/about-claude/models/overview",
        "https://docs.anthropic.com/en/docs/about-claude/pricing",
        "https://docs.anthropic.com/en/api/messages",
        "https://docs.anthropic.com/en/docs/build-with-claude/streaming",
        "https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking",
        "https://docs.anthropic.com/en/docs/build-with-claude/vision",
        "https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview",
        "`ANTHROPIC_API_KEY`",
        "`https://api.anthropic.com`",
        "`claude-opus-4-8`",
        "`claude-sonnet-4-6`",
        "uv run pytest tests/ai/test_curated_catalog.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_baidu_qianfan_evidence_matches_curated_provider_fixture() -> None:
    text = BAIDU_QIANFAN_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: baidu-qianfan",
        "- Verified at: 2026-06-22",
        "- Issue: #107",
        "https://cloud.baidu.com/doc/qianfan-api/s/Dmba8k71y",
        "https://cloud.baidu.com/doc/qianfan-api/s/3m7of64lb",
        "https://cloud.baidu.com/doc/qianfan-api/s/ym9chdsy5",
        "https://cloud.baidu.com/doc/qianfan-docs/s/Wm95lyynv",
        "https://cloud.baidu.com/doc/qianfan-docs/s/xm95lyys5",
        "`QIANFAN_API_KEY`",
        "`BAIDU_QIANFAN_API_KEY`",
        "`https://qianfan.baidubce.com/v2`",
        "`ernie-5.1`",
        "248,832 token context and 65,536 maximum answer tokens",
        "CNY 6 input and CNY 22 output",
        "lower <=32K pricing tier is omitted",
        "uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_moonshot_evidence_matches_curated_provider_fixture() -> None:
    text = MOONSHOT_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: moonshot",
        "- Verified at: 2026-06-22",
        "https://platform.kimi.ai/docs/models",
        "https://platform.kimi.ai/docs/models/kimi-k2.6",
        "https://platform.kimi.ai/docs/models/kimi-k2.7-code",
        "https://platform.kimi.ai/docs/quickstart",
        "https://platform.kimi.ai/docs/api-reference",
        "https://platform.kimi.ai/",
        "`MOONSHOT_API_KEY`",
        "`https://api.moonshot.ai/v1`",
        "`kimi-k2.6`",
        "`kimi-k2.7-code`",
        "Legacy duplicate China/global/coding endpoint variants",
        "uv run pytest tests/ai/test_curated_catalog.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_dashscope_evidence_matches_curated_provider_fixture() -> None:
    text = DASHSCOPE_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: dashscope",
        "- Verified at: 2026-06-22",
        "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
        "https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses",
        "https://help.aliyun.com/zh/model-studio/getting-started/models",
        "https://help.aliyun.com/zh/model-studio/model-pricing",
        "`DASHSCOPE_API_KEY`",
        "`https://dashscope.aliyuncs.com/compatible-mode/v1`",
        "`qwen3.7-max`",
        "`qwen3.7-plus`",
        "China North 2 Beijing endpoint",
        "uv run pytest tests/ai/test_curated_catalog.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_deepseek_evidence_matches_curated_provider_fixture() -> None:
    text = DEEPSEEK_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: deepseek",
        "- Verified at: 2026-06-22",
        "- Issue: #104",
        "https://api-docs.deepseek.com/",
        "https://api-docs.deepseek.com/quick_start/pricing",
        "https://api-docs.deepseek.com/guides/thinking_mode",
        "https://api-docs.deepseek.com/api/create-chat-completion",
        "`DEEPSEEK_API_KEY`",
        "`https://api.deepseek.com`",
        "`deepseek-v4-flash`",
        "`deepseek-v4-pro`",
        "1,000,000 token context, 384,000 maximum output tokens",
        "$0.14 input, $0.0028 cache hit, and $0.28 output",
        "$0.435 input, $0.003625 cache hit, and $0.87 output",
        "uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_minimax_evidence_matches_curated_provider_fixture() -> None:
    text = MINIMAX_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: minimax",
        "- Verified at: 2026-06-22",
        "- Issue: #105",
        "https://platform.minimax.io/docs/api-reference/api-overview",
        "https://platform.minimax.io/docs/pricing/overview",
        "https://platform.minimax.io/docs/guides/text-models",
        "`MINIMAX_API_KEY`",
        "`https://api.minimax.io/anthropic/v1`",
        "`MiniMax-M3`",
        "1,000,000 token context",
        "$0.60 input, $0.12 cache hit, and $2.40 output",
        "lower <=512K pricing tier is omitted",
        "uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_anthropic_messages_mapping.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_openai_evidence_matches_curated_provider_fixture() -> None:
    text = OPENAI_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: openai",
        "- Verified at: 2026-06-22",
        "https://developers.openai.com/api/docs/models",
        "https://developers.openai.com/api/docs/guides/latest-model",
        "https://developers.openai.com/api/reference/resources/responses/methods/create",
        "https://developers.openai.com/api/docs/pricing",
        "`OPENAI_API_KEY`",
        "`https://api.openai.com/v1`",
        "`gpt-5.5`",
        "`gpt-5.4-mini`",
        "uv run pytest tests/ai/test_curated_catalog.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_tencent_hunyuan_evidence_matches_curated_provider_fixture() -> None:
    text = TENCENT_HUNYUAN_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: tencent-hunyuan",
        "- Verified at: 2026-06-22",
        "- Issue: #102",
        "https://cloud.tencent.com/document/product/1729/111007",
        "https://cloud.tencent.com/document/product/1729/104753",
        "https://cloud.tencent.com/document/product/1729/97731",
        "`HUNYUAN_API_KEY`",
        "`https://api.hunyuan.cloud.tencent.com/v1`",
        "`hunyuan-turbos-latest`",
        "32K maximum input and 16K maximum output",
        "CNY 0.8 input and CNY 2 output",
        "uv run pytest tests/ai/test_curated_catalog.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_volcano_ark_evidence_matches_curated_provider_fixture() -> None:
    text = VOLCANO_ARK_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: volcano-ark",
        "- Verified at: 2026-06-22",
        "- Issue: #106",
        "https://www.volcengine.com/docs/82379/1330310",
        "https://www.volcengine.com/docs/82379/1949118",
        "https://www.volcengine.com/docs/82379/1544106",
        "`ARK_API_KEY`",
        "`https://ark.cn-beijing.volces.com/api/v3`",
        "`doubao-seed-2-0-lite-260215`",
        "256K context",
        "`pricing` is omitted",
        "`reasoning` is false",
        "uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_zai_evidence_matches_curated_provider_fixture() -> None:
    text = ZAI_EVIDENCE_PATH.read_text(encoding="utf-8")

    for expected in [
        "# Provider evidence: zai",
        "- Verified at: 2026-06-22",
        "- Issue: #103",
        "https://docs.z.ai/guides/overview/quick-start",
        "https://docs.z.ai/guides/llm/glm-5.2",
        "https://docs.z.ai/guides/llm/glm-5.1",
        "https://docs.z.ai/guides/overview/pricing",
        "https://docs.z.ai/guides/capabilities/struct-output",
        "https://docs.z.ai/guides/capabilities/function-call",
        "`ZAI_API_KEY`",
        "`https://api.z.ai/api/paas/v4/`",
        "`glm-5.2`",
        "`glm-5.1`",
        "$1.4 input, $0.26 cached input, and $4.4 output",
        "coding-plan endpoint is omitted",
        "uv run pytest tests/ai/test_curated_catalog.py tests/providers/test_openai_completions_provider.py -q",
        "Not run on 2026-06-22",
    ]:
        assert expected in text


def test_curated_provider_matrix_matches_openai_fixture() -> None:
    text = CURATED_PROVIDER_MATRIX_PATH.read_text(encoding="utf-8")

    assert "`anthropic` | `anthropic-messages` | `anthropic-messages`" in text
    assert "`claude-opus-4-8`, `claude-sonnet-4-6`" in text
    assert "`ANTHROPIC_API_KEY`" in text
    assert "`catalog-evidence/anthropic.md`" in text
    assert "`dashscope` | `openai-responses` | `openai-responses`" in text
    assert "`qwen3.7-max`, `qwen3.7-plus`" in text
    assert "`DASHSCOPE_API_KEY`" in text
    assert "`catalog-evidence/dashscope.md`" in text
    assert "`deepseek` | `openai-completions` | `openai-completions`" in text
    assert "`deepseek-v4-flash`, `deepseek-v4-pro`" in text
    assert "`DEEPSEEK_API_KEY`" in text
    assert "`catalog-evidence/deepseek.md`" in text
    assert "`minimax` | `anthropic-messages` | `anthropic-messages`" in text
    assert "`MiniMax-M3`" in text
    assert "`MINIMAX_API_KEY`" in text
    assert "`catalog-evidence/minimax.md`" in text
    assert "`moonshot` | `openai-completions` | `openai-completions`" in text
    assert "`kimi-k2.6`, `kimi-k2.7-code`" in text
    assert "`MOONSHOT_API_KEY`" in text
    assert "`catalog-evidence/moonshot.md`" in text
    assert "`openai` | `openai-responses` | `openai-responses`" in text
    assert "`gpt-5.5`, `gpt-5.4-mini`" in text
    assert "`OPENAI_API_KEY`" in text
    assert "`catalog-evidence/openai.md`" in text
    assert "`tencent-hunyuan` | `openai-completions` | `openai-completions`" in text
    assert "`hunyuan-turbos-latest`" in text
    assert "`HUNYUAN_API_KEY`" in text
    assert "`catalog-evidence/tencent-hunyuan.md`" in text
    assert "`volcano-ark` | `openai-completions-cn-beijing` | `openai-completions`" in text
    assert "`doubao-seed-2-0-lite-260215`" in text
    assert "`ARK_API_KEY`" in text
    assert "`catalog-evidence/volcano-ark.md`" in text
    assert "`zai` | `openai-completions` | `openai-completions`" in text
    assert "`glm-5.2`, `glm-5.1`" in text
    assert "`ZAI_API_KEY`" in text
    assert "`catalog-evidence/zai.md`" in text
    assert "load_model_registry_from_file" in text
