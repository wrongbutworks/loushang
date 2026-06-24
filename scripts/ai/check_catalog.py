from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from loushang.ai.model import load_model_registry_from_file
from loushang.ai.model.loader import validate_model_registry_raw

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "src/loushang/ai/model/models.json"


def main() -> int:
    errors = check_catalog()
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    registry = load_model_registry_from_file(CATALOG_PATH)
    print(
        json.dumps(
            {
                "providers": len(registry.list_providers()),
                "endpoints": len(registry.list_endpoints()),
                "models": len(registry.list_models()),
                "catalog": CATALOG_PATH.relative_to(REPO_ROOT).as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


def check_catalog() -> list[str]:
    errors: list[str] = []
    raw = _load_catalog_raw()
    try:
        validate_model_registry_raw(raw)
    except Exception as exc:  # pragma: no cover - exercised by script failure path
        errors.append(f"catalog schema validation failed: {exc}")
        return errors

    registry = load_model_registry_from_file(CATALOG_PATH)
    providers = registry.list_providers()
    endpoints = registry.list_endpoints()
    models = registry.list_models()

    for provider in providers:
        preferred_by_model: dict[str, list[str]] = {}
        for endpoint in registry.list_endpoints(provider=provider.id):
            if not endpoint.preferred:
                continue
            for model_id in endpoint.models:
                preferred_by_model.setdefault(model_id, []).append(endpoint.id)
        duplicates = {
            model_id: endpoint_ids
            for model_id, endpoint_ids in preferred_by_model.items()
            if len(endpoint_ids) > 1
        }
        if duplicates:
            errors.append(
                f"provider {provider.id} has duplicate preferred endpoints: {duplicates}"
            )

    unsupported_modalities = sorted(
        {
            modality
            for model in models
            for modality in (*model.capabilities.input, *model.capabilities.output)
            if modality not in {"text", "image"}
        }
    )
    if unsupported_modalities:
        errors.append(f"unsupported modalities in catalog: {unsupported_modalities}")

    if not endpoints:
        errors.append("catalog has no endpoints")
    return errors


def _load_catalog_raw() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

if __name__ == "__main__":
    raise SystemExit(main())
