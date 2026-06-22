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
MOONSHOT_EVIDENCE_PATH = EVIDENCE_DIR / "moonshot.md"
OPENAI_EVIDENCE_PATH = EVIDENCE_DIR / "openai.md"
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
        "moonshot",
        "openai",
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
    assert len(registry.list_models(provider="moonshot")) > len(
        _load_curated_registry().list_models(provider="moonshot")
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


def test_curated_provider_matrix_matches_openai_fixture() -> None:
    text = CURATED_PROVIDER_MATRIX_PATH.read_text(encoding="utf-8")

    assert "`anthropic` | `anthropic-messages` | `anthropic-messages`" in text
    assert "`claude-opus-4-8`, `claude-sonnet-4-6`" in text
    assert "`ANTHROPIC_API_KEY`" in text
    assert "`catalog-evidence/anthropic.md`" in text
    assert "`moonshot` | `openai-completions` | `openai-completions`" in text
    assert "`kimi-k2.6`, `kimi-k2.7-code`" in text
    assert "`MOONSHOT_API_KEY`" in text
    assert "`catalog-evidence/moonshot.md`" in text
    assert "`openai` | `openai-responses` | `openai-responses`" in text
    assert "`gpt-5.5`, `gpt-5.4-mini`" in text
    assert "`OPENAI_API_KEY`" in text
    assert "`catalog-evidence/openai.md`" in text
    assert "load_model_registry_from_file" in text
