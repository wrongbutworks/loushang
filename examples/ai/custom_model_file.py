"""Offline custom model file example.

This example writes the current `models.json` shape to a temporary file, loads
it into a standalone registry, and queries the custom model. It does not call a
remote API.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from loushang.ai.model import load_model_registry_from_file

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
        models = registry.list_models(provider="company")

    return {
        "availableModels": [
            f"{item.provider_id}:{item.endpoint_id}:{item.id}" for item in models
        ],
        "model": f"{model.provider_id}:{model.endpoint_id}:{model.id}",
        "displayName": model.name,
        "upstreamId": model.upstream_id,
        "capabilities": {
            "stream": model.supports_stream,
            "toolUse": model.supports_tool_use,
        },
    }


def main() -> None:
    print(json.dumps(inspect_custom_model_file(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
