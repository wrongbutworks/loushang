from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from loushang.ai import CallOptions, complete
from loushang.ai.api_registry import ApiProviderRegistry
from loushang.ai.model import (
    load_layered_model_registry,
    load_model_registry_from_file,
)
from loushang.ai.providers.faux import FauxProvider


def _custom_model_raw() -> dict[str, object]:
    return {
        "providers": {
            "company": {
                "displayName": "Company AI",
                "auth": {"apiKeyEnv": "COMPANY_AI_API_KEY"},
                "endpoints": {
                    "anthropic-messages": {
                        "api": "anthropic-messages",
                        "baseUrl": "https://models.company.example",
                        "adapter": {
                            "fineGrainedTools": True,
                            "longCacheRetention": False,
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


def _write_model_file(directory: Path, raw: dict[str, object]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "company.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_json_only_custom_model_loads_merges_queries_and_completes(
    tmp_path: Path,
) -> None:
    user_model_dir = tmp_path / "models"
    path = _write_model_file(user_model_dir, _custom_model_raw())

    custom_registry = load_model_registry_from_file(path)
    custom_model = custom_registry.get_model(
        "company",
        "anthropic-messages",
        "company-chat",
    )
    assert custom_model.upstream_id == "vendor/company-chat-2026-06"
    assert custom_model.supports_stream is True
    assert custom_model.supports_tool_use is True

    layered = load_layered_model_registry(user_dir=user_model_dir)
    assert layered.get_model("openai", "openai-responses", "gpt-5.5").id == "gpt-5.5"
    model = layered.get_model("company", "anthropic-messages", "company-chat")
    assert model.base_url == "https://models.company.example"
    assert model.upstream_id == "vendor/company-chat-2026-06"

    provider_registry = ApiProviderRegistry()
    provider_registry.register_api_provider(FauxProvider())

    async def run_complete():
        return await complete(
            model,
            {"messages": [{"role": "user", "content": "hello"}]},
            CallOptions(api_key="test-key"),
            registry=provider_registry,
        )

    message = asyncio.run(run_complete())

    assert message.provider == "company"
    assert message.api == "anthropic-messages"
    assert message.model == "company-chat"
    assert message.response_id == "faux-response"
    assert message.content[0].text == "mock hello from faux provider"


def test_custom_model_file_rejects_invalid_adapter_field(tmp_path: Path) -> None:
    raw = _custom_model_raw()
    providers = raw["providers"]
    assert isinstance(providers, dict)
    company = providers["company"]
    assert isinstance(company, dict)
    endpoints = company["endpoints"]
    assert isinstance(endpoints, dict)
    endpoint = endpoints["anthropic-messages"]
    assert isinstance(endpoint, dict)
    endpoint["adapter"] = {"maxOutputTokensField": "max_tokens"}

    path = _write_model_file(tmp_path, raw)

    with pytest.raises(ValueError, match="unknown keys") as exc_info:
        load_model_registry_from_file(path)

    assert str(path) in str(exc_info.value)


def test_layered_registry_rejects_duplicate_builtin_full_model_id(
    tmp_path: Path,
) -> None:
    raw = _custom_model_raw()
    providers = raw["providers"]
    assert isinstance(providers, dict)
    providers.clear()
    providers["moonshot"] = {
        "endpoints": {
            "openai-completions": {
                "api": "openai-completions",
                "baseUrl": "https://models.company.example/v1",
                "adapter": {"developerRole": False},
                "models": {
                    "kimi-k2.6": {
                        "capabilities": {
                            "input": ["text"],
                            "output": ["text"],
                        }
                    }
                },
            }
        }
    }
    path = _write_model_file(tmp_path, raw)

    with pytest.raises(ValueError, match="duplicate model id") as exc_info:
        load_layered_model_registry(user_dir=tmp_path)

    message = str(exc_info.value)
    assert str(path) in message
    assert "<builtin>" in message
