from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loushang.ai.model import (
    ModelRegistry,
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

MAX_PROVIDERS = 11
MAX_ENDPOINTS = 16
MAX_MODELS = 20
MAX_MODELS_PER_PROVIDER = 2


def _load_curated_raw() -> dict[str, Any]:
    return json.loads(CURATED_CATALOG_PATH.read_text(encoding="utf-8"))


def _load_curated_registry() -> ModelRegistry:
    return load_model_registry_from_file(CURATED_CATALOG_PATH)


def test_curated_catalog_is_empty_v2_skeleton() -> None:
    raw = _load_curated_raw()

    assert raw == {"schemaVersion": 2, "providers": {}}
    validate_model_registry_raw(raw)
    assert _load_curated_registry().list_providers() == []


def test_default_builtin_catalog_still_uses_legacy_catalog() -> None:
    registry = load_builtin_model_registry()

    assert registry.list_providers()
    assert registry.get_provider("openai") is not None
    assert _load_curated_registry().get_provider("openai") is None


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
