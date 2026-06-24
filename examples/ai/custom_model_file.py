"""Offline custom model file example.

This example writes the current `models.json` shape to a temporary file, loads
it into a standalone registry, and inspects the resolved provider request. It
does not call a remote API.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from loushang.ai.model import load_model_registry_from_file
from loushang.ai.provider import resolve_request_for_model

CUSTOM_MODEL_FILE = {
    "providers": {
        "company": {
            "displayName": "Company AI",
            "auth": {"apiKeyEnv": "COMPANY_AI_API_KEY"},
            "endpoints": {
                "openai-completions": {
                    "api": "openai-completions",
                    "baseUrl": "https://models.company.example/v1",
                    "adapter": {
                        "developerRole": False,
                        "maxOutputTokensField": "max_completion_tokens",
                        "reasoningFormat": "openai",
                    },
                    "models": {
                        "company-chat": {
                            "displayName": "Company Chat",
                            "upstreamId": "vendor/company-chat-2026-06",
                            "capabilities": {
                                "input": ["text"],
                                "output": ["text"],
                                "stream": True,
                                "toolUse": True,
                            },
                        }
                    },
                }
            },
        }
    }
}


def inspect_custom_model_file() -> dict[str, object]:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "company-models.json"
        path.write_text(json.dumps(CUSTOM_MODEL_FILE), encoding="utf-8")

        registry = load_model_registry_from_file(path)
        model = registry.get_model("company", "openai-completions", "company-chat")
        request = resolve_request_for_model(
            model,
            registry=registry,
            env={},
        )

    return {
        "model": f"{model.provider_id}:{model.endpoint_id}:{model.id}",
        "api": request.api,
        "baseUrl": request.base_url,
        "upstreamModelId": request.upstream_model_id,
        "adapter": (
            request.adapter_config.to_raw()
            if hasattr(request.adapter_config, "to_raw")
            else None
        ),
    }


def main() -> None:
    print(json.dumps(inspect_custom_model_file(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
