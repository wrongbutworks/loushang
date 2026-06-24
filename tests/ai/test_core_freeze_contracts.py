from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

import loushang.ai as ai
from loushang.ai.model import (
    clear_default_model_registry,
    get_default_model_registry,
    load_model_registry_from_file,
)
from loushang.ai.options import CallOptions
from loushang.ai.provider.resolution import resolve_request_for_model

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SRC = REPO_ROOT / "src/loushang/ai"
MODEL_DIR = AI_SRC / "model"


def _custom_registry_raw(provider_id: str = "company-aif002") -> dict[str, object]:
    return {
        "providers": {
            provider_id: {
                "displayName": "Company AI",
                "auth": {"apiKeyEnv": "COMPANY_AI_API_KEY"},
                "endpoints": {
                    "anthropic-messages": {
                        "api": "anthropic-messages",
                        "baseUrl": "https://ai.company.example/v1",
                        "models": {
                            "company-chat": {
                                "displayName": "Company Chat",
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                    "contextWindow": 1024,
                                    "maxTokens": 128,
                                    "stream": False,
                                },
                            }
                        },
                    }
                },
            }
        }
    }


def _write_custom_registry(path: Path, provider_id: str = "company-aif002") -> None:
    path.write_text(
        json.dumps(_custom_registry_raw(provider_id), indent=2),
        encoding="utf-8",
    )


@pytest.mark.xfail(strict=True, reason="AIF-004 removes legacy Compat types")
def test_no_legacy_compat_model_contract_types_remain() -> None:
    import loushang.ai.model as model_module

    forbidden_exports = {
        "Compat",
        "EndpointProtocolFeatures",
        "EndpointWireDialect",
        "SupportStatus",
    }
    assert forbidden_exports.isdisjoint(model_module.__all__)
    for name in forbidden_exports:
        assert not hasattr(model_module, name)

    forbidden_source_tokens = (
        "class Compat",
        "SupportStatus",
        "EndpointProtocol",
        "EndpointWireDialect",
        "compat_schema",
    )
    for path in (MODEL_DIR).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_source_tokens:
            assert token not in text, (path, token)


@pytest.mark.xfail(strict=True, reason="AIF-003 establishes models.json only")
def test_builtin_model_file_is_models_json_without_schema_version() -> None:
    models_json = MODEL_DIR / "models.json"
    legacy_catalog = MODEL_DIR / "models.curated.v2.json"
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert models_json.is_file()
    assert not legacy_catalog.exists()
    assert '"loushang.ai.model" = ["models.json"]' in pyproject
    assert "models.curated.v2.json" not in pyproject

    raw = json.loads(models_json.read_text(encoding="utf-8"))
    assert "schemaVersion" not in raw
    for path in MODEL_DIR.rglob("*.py"):
        assert "schemaVersion" not in path.read_text(encoding="utf-8"), path


@pytest.mark.xfail(strict=True, reason="AIF-009 removes Simple API")
def test_simple_api_is_not_part_of_root_or_api_contract() -> None:
    forbidden = {
        "SimpleCallOptions",
        "SimpleStreamOptions",
        "ThinkingBudgets",
        "complete_simple",
        "stream_simple",
        "simple_options_to_call_options",
    }
    for name in forbidden:
        assert name not in ai.__all__
        assert not hasattr(ai, name)

    import loushang.ai.api as api_module
    import loushang.ai.options as options_module

    for name in forbidden:
        assert not hasattr(api_module, name)
        assert not hasattr(options_module, name)


@pytest.mark.xfail(
    strict=True,
    reason="AIF-009 removes deprecated provider-specific core options",
)
def test_deprecated_provider_specific_options_are_not_core_api() -> None:
    import loushang.ai.advanced as advanced_module

    forbidden = {
        "AnthropicOptions",
        "OpenAICompletionsOptions",
        "OpenAIResponsesOptions",
    }
    for name in forbidden:
        assert not hasattr(advanced_module, name)
    assert not (AI_SRC / "advanced/options.py").exists()


def test_default_registry_loads_builtin_and_user_model_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_model_dir = tmp_path / ".loushang" / "models"
    user_model_dir.mkdir(parents=True)
    _write_custom_registry(user_model_dir / "company.json")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    clear_default_model_registry()

    try:
        registry = get_default_model_registry()
        assert registry.get_provider("openai") is not None
        model = registry.get_model(
            "company-aif002",
            "anthropic-messages",
            "company-chat",
        )
        assert model.api == "anthropic-messages"
        assert model.base_url == "https://ai.company.example/v1"
    finally:
        clear_default_model_registry()


@pytest.mark.xfail(
    strict=True,
    reason="AIF-008 adds ProviderRequest.mode and invoke_raw",
)
def test_provider_contract_has_complete_and_stream_invocation_modes() -> None:
    from loushang.ai.provider.protocol import ApiProvider, ProviderRequest

    field_names = {field.name for field in fields(ProviderRequest)}

    assert {
        "call_id",
        "mode",
        "model",
        "context",
        "headers",
        "max_output_tokens",
        "temperature",
        "timeout",
        "retry",
        "reasoning",
        "tool_choice",
        "structured_output",
    } <= field_names
    assert "resolved" not in field_names
    assert hasattr(ApiProvider, "invoke_raw")
    assert not hasattr(ApiProvider, "stream_raw")


@pytest.mark.xfail(
    strict=True,
    reason="AIF-005 makes Model carry call info without private endpoint refs",
)
def test_model_carries_call_information_without_registry_lookup_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "company.json"
    _write_custom_registry(path)
    model = load_model_registry_from_file(path).get_model(
        "company-aif002",
        "anthropic-messages",
        "company-chat",
    )

    assert model.api == "anthropic-messages"
    assert model.base_url == "https://ai.company.example/v1"
    assert model.auth is not None
    assert model.auth.api_key_env == "COMPANY_AI_API_KEY"
    assert model.upstream_id is None
    for name in (
        "_endpoint_ref",
        "_auth_inherited",
        "_compat_overrides",
        "_transport_legacy_raw",
        "_routing_legacy_raw",
        "_raw_source",
    ):
        assert not hasattr(model, name)
    assert not hasattr(type(model), "with_endpoint")
    assert not hasattr(type(model), "with_contract_overrides")


def test_bound_model_resolves_without_default_registry_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "company.json"
    _write_custom_registry(path)
    model = load_model_registry_from_file(path).get_model(
        "company-aif002",
        "anthropic-messages",
        "company-chat",
    )

    def fail_default_registry_lookup():
        raise AssertionError("default registry lookup should not be needed")

    monkeypatch.setattr(
        "loushang.ai.provider.resolution.get_default_model_registry",
        fail_default_registry_lookup,
    )

    request = resolve_request_for_model(
        model,
        options=CallOptions(api_key="test-key"),
        env={},
    )

    assert request.provider == "company-aif002"
    assert request.endpoint == "anthropic-messages"
    assert request.api == "anthropic-messages"
    assert request.base_url == "https://ai.company.example/v1"
