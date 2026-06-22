"""Offline smoke check for the built-in curated provider catalog."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from loushang.ai import get_model, list_models


def _load_provider_examples():
    path = Path(__file__).with_name("11_provider_matrix.py")
    spec = importlib.util.spec_from_file_location("_examples_ai_provider_matrix", path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise RuntimeError(f"Cannot load provider matrix from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.PROVIDER_EXAMPLES


PROVIDER_EXAMPLES = _load_provider_examples()


def inspect_provider_smoke() -> dict[str, object]:
    providers: list[dict[str, object]] = []
    for example in PROVIDER_EXAMPLES:
        model = get_model(example.provider_id, example.endpoint_id, example.model_id)
        providers.append(
            {
                "provider": model.provider_id,
                "endpoint": model.endpoint_id,
                "model": model.id,
                "api": model.api,
                "env": list(example.env_vars),
                "stream": model.supports_stream,
                "tools": model.supports_tool_use,
            }
        )
    return {
        "providerCount": len(PROVIDER_EXAMPLES),
        "modelCount": len(list_models()),
        "providers": providers,
    }


def main() -> None:
    print(json.dumps(inspect_provider_smoke(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
