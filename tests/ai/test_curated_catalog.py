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
        "openai"
    ]


def test_default_builtin_catalog_still_uses_legacy_catalog() -> None:
    registry = load_builtin_model_registry()

    assert registry.list_providers()
    assert registry.get_provider("openai") is not None
    assert len(registry.list_models(provider="openai")) > len(
        _load_curated_registry().list_models(provider="openai")
    )


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

    assert "`openai` | `openai-responses` | `openai-responses`" in text
    assert "`gpt-5.5`, `gpt-5.4-mini`" in text
    assert "`OPENAI_API_KEY`" in text
    assert "`catalog-evidence/openai.md`" in text
    assert "load_model_registry_from_file" in text
