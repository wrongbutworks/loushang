"""Offline smoke check for the built-in curated provider catalog."""

from __future__ import annotations

import json

from provider_matrix import PROVIDER_EXAMPLES

from loushang.ai import get_model, list_models


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
