from __future__ import annotations

import json
from pathlib import Path

import pytest

from loushang.ai.model import (
    AnthropicMessagesConfig,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
    load_builtin_model_registry,
    load_layered_model_registry,
    load_model_registry,
    load_model_registry_from_directory,
    load_model_registry_from_file,
    validate_model_registry_raw,
)


def _capabilities() -> dict[str, object]:
    return {
        "contextWindow": 128000,
        "maxTokens": 8192,
        "input": ["text"],
        "output": ["text"],
        "reasoning": True,
        "stream": True,
        "toolUse": True,
        "structuredOutput": True,
        "attachment": False,
        "temperature": True,
    }


def _model_raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "displayName": "Test Model",
        "capabilities": _capabilities(),
    }
    raw.update(overrides)
    return raw


def _registry_raw(
    *,
    provider_id: str = "custom",
    api: str = "openai-completions",
    endpoint_adapter: dict[str, object] | None = None,
    model_adapter: dict[str, object] | None = None,
    endpoint_extra: dict[str, object] | None = None,
    model_extra: dict[str, object] | None = None,
) -> dict[str, object]:
    endpoint: dict[str, object] = {
        "api": api,
        "baseUrl": "https://example.test/v1",
        "models": {
            "test-model": _model_raw(
                **({"adapter": model_adapter} if model_adapter is not None else {}),
                **(model_extra or {}),
            )
        },
    }
    if endpoint_adapter is not None:
        endpoint["adapter"] = endpoint_adapter
    endpoint.update(endpoint_extra or {})
    return {
        "providers": {
            provider_id: {
                "displayName": "Custom",
                "auth": {"kind": "apiKey", "apiKeyEnv": "TEST_API_KEY"},
                "endpoints": {"test-endpoint": endpoint},
            }
        }
    }


def _write_registry(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _set_nested(
    raw: dict[str, object],
    path: tuple[str, ...],
    value: object,
) -> None:
    target: object = raw
    for key in path[:-1]:
        assert isinstance(target, dict)
        target = target[key]
    assert isinstance(target, dict)
    target[path[-1]] = value


def test_builtin_model_registry_loads_adapter_configs() -> None:
    registry = load_builtin_model_registry()

    adapter_types = {type(model.adapter) for model in registry.list_models()}

    assert OpenAICompletionsConfig in adapter_types
    assert OpenAIResponsesConfig in adapter_types
    assert AnthropicMessagesConfig in adapter_types


def test_registry_rejects_root_schema_version() -> None:
    raw = _registry_raw(endpoint_adapter={"developerRole": False})
    raw["schemaVersion"] = 2

    with pytest.raises(ValueError, match="no longer supported"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize("removed_field", ["compat", "protocol", "dialect"])
def test_registry_rejects_removed_endpoint_fields(removed_field: str) -> None:
    raw = _registry_raw(
        endpoint_adapter={"developerRole": False},
        endpoint_extra={removed_field: {}},
    )

    with pytest.raises(ValueError, match="no longer supported"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize("removed_field", ["compat", "protocol", "dialect"])
def test_registry_rejects_removed_model_fields(removed_field: str) -> None:
    raw = _registry_raw(
        endpoint_adapter={"developerRole": False},
        model_extra={removed_field: {}},
    )

    with pytest.raises(ValueError, match="no longer supported"):
        validate_model_registry_raw(raw)


def test_registry_rejects_unknown_adapter_field() -> None:
    raw = _registry_raw(endpoint_adapter={"futureFlag": True})

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


def test_registry_rejects_reserved_extra_body_fields() -> None:
    raw = _registry_raw(endpoint_adapter={"extraBody": {"model": "other"}})

    with pytest.raises(ValueError, match="invalid adapter config"):
        validate_model_registry_raw(raw)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("providers", "custom"), "bad", "must be an object"),
        (("providers", "custom", "displayName"), "", "non-empty string"),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "api"),
            "",
            "non-empty string",
        ),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "preferred"),
            "yes",
            "must be a boolean",
        ),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "auth"),
            {"apiKeyEnvs": [""]},
            "string list",
        ),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "auth"),
            {"extraHeaders": {"x-test": 1}},
            "string map",
        ),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "transport"),
            {"fallback": "yes"},
            "must be a boolean",
        ),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "transport"),
            {"timeout": 0},
            "positive number",
        ),
        (
            ("providers", "custom", "endpoints", "test-endpoint", "routing"),
            {"requestOverrides": {"": {}}},
            "non-empty string",
        ),
        (
            (
                "providers",
                "custom",
                "endpoints",
                "test-endpoint",
                "models",
                "test-model",
                "pricing",
            ),
            {"input": -1},
            "non-negative number",
        ),
        (
            (
                "providers",
                "custom",
                "endpoints",
                "test-endpoint",
                "models",
                "test-model",
                "upstreamId",
            ),
            " ",
            "non-empty string",
        ),
        (
            (
                "providers",
                "custom",
                "endpoints",
                "test-endpoint",
                "models",
                "test-model",
                "capabilities",
                "input",
            ),
            ["audio"],
            "invalid modalities",
        ),
    ],
)
def test_registry_rejects_invalid_catalog_boundary_values(
    path: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    raw = _registry_raw(endpoint_adapter={"developerRole": False})
    _set_nested(raw, path, value)

    with pytest.raises(ValueError, match=message):
        validate_model_registry_raw(raw)


def test_registry_rejects_endpoint_with_both_auth_shapes() -> None:
    raw = _registry_raw(endpoint_adapter={"developerRole": False})
    endpoint = raw["providers"]["custom"]["endpoints"]["test-endpoint"]
    assert isinstance(endpoint, dict)
    endpoint["auth"] = {"apiKeyEnv": "ENDPOINT_KEY"}
    endpoint["authOverride"] = {"apiKeyEnv": "OVERRIDE_KEY"}

    with pytest.raises(ValueError, match="cannot define both auth and authOverride"):
        validate_model_registry_raw(raw)


def test_registry_rejects_adapter_for_unsupported_api() -> None:
    raw = _registry_raw(api="custom-api", endpoint_adapter={"developerRole": False})

    with pytest.raises(ValueError, match="not supported for api"):
        validate_model_registry_raw(raw)


def test_openai_style_endpoint_requires_adapter_for_custom_base_url() -> None:
    raw = _registry_raw(endpoint_adapter=None)

    with pytest.raises(ValueError, match="must declare adapter"):
        validate_model_registry_raw(raw)


def test_model_adapter_json_override_is_shallow(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        _registry_raw(
            endpoint_adapter={
                "developerRole": False,
                "maxOutputTokensField": "max_tokens",
            },
            model_adapter={"reasoningFormat": "moonshot"},
        ),
    )

    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "test-endpoint", "test-model")

    assert isinstance(model.adapter, OpenAICompletionsConfig)
    assert model.adapter.developer_role is False
    assert model.adapter.max_output_tokens_field == "max_tokens"
    assert model.adapter.reasoning_format == "moonshot"


def test_model_adapter_json_override_can_restore_default_value(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        _registry_raw(
            endpoint_adapter={"developerRole": False},
            model_adapter={"developerRole": True},
        ),
    )

    registry = load_model_registry_from_file(path)
    model = registry.get_model("custom", "test-endpoint", "test-model")

    assert isinstance(model.adapter, OpenAICompletionsConfig)
    assert model.adapter.developer_role is True


def test_openai_responses_adapter_schema_accepts_core_fields(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        _registry_raw(
            provider_id="openai",
            api="openai-responses",
            endpoint_adapter={
                "developerRole": True,
                "promptCacheKey": True,
                "sessionIdHeader": True,
                "longCacheRetention": True,
            },
        ),
    )

    model = load_model_registry_from_file(path).get_model(
        "openai",
        "test-endpoint",
        "test-model",
    )

    assert isinstance(model.adapter, OpenAIResponsesConfig)
    assert model.adapter.prompt_cache_key is True


def test_anthropic_adapter_schema_accepts_tristate_fields(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        _registry_raw(
            api="anthropic-messages",
            endpoint_adapter={
                "fineGrainedTools": True,
                "interleavedThinking": False,
                "sessionAffinityHeaders": True,
                "longCacheRetention": False,
            },
        ),
    )

    model = load_model_registry_from_file(path).get_model(
        "custom",
        "test-endpoint",
        "test-model",
    )

    assert isinstance(model.adapter, AnthropicMessagesConfig)
    assert model.adapter.fine_grained_tools is True
    assert model.adapter.interleaved_thinking is False


def test_load_registry_merges_adapter_auth_transport_and_defaults(
    tmp_path: Path,
) -> None:
    raw = _registry_raw(
        endpoint_adapter={
            "developerRole": False,
            "maxOutputTokensField": "max_tokens",
            "reasoningEffort": True,
        },
        model_adapter={"reasoningFormat": "moonshot"},
        endpoint_extra={
            "lane": "coding",
            "auth": {
                "apiKeyEnv": "ENDPOINT_KEY",
                "extraHeaders": {"x-endpoint": "endpoint"},
            },
            "transport": {"kind": "httpx", "fallback": True, "timeout": 30},
            "routing": {"requestOverrides": {"openrouter": {"order": ["a"]}}},
        },
        model_extra={
            "authOverride": {
                "apiKeyEnv": "MODEL_KEY",
                "extraHeaders": {"x-model": "model"},
            },
            "transport": {"timeout": 5},
            "routing": {"requestOverrides": {"openrouter": {"only": ["b"]}}},
            "upstreamId": "vendor/test-model",
        },
    )

    model = load_model_registry_from_file(_write_registry(tmp_path, raw)).get_model(
        "custom",
        "test-endpoint",
        "test-model",
    )

    assert model.api == "openai-completions"
    assert isinstance(model.adapter, OpenAICompletionsConfig)
    assert model.adapter.developer_role is False
    assert model.adapter.max_output_tokens_field == "max_tokens"
    assert model.adapter.reasoning_format == "moonshot"
    assert model.auth is not None
    assert model.auth.api_key_env == "MODEL_KEY"
    assert model.auth.extra_headers == {"x-endpoint": "endpoint", "x-model": "model"}
    assert isinstance(model.defaults.get("maxOutputTokens"), int)
    assert model.defaults.get("reasoningEffort") == "medium"
    assert model.defaults.get("temperature") == 0.2
    assert model.defaults.get("contextWindow") == 128000
    assert model.transport.kind == "httpx"
    assert model.transport.fallback is True
    assert model.transport.timeout == 5
    assert model.routing.request_overrides == {
        "openrouter": {"order": ["a"], "only": ["b"]}
    }
    assert model.upstream_id == "vendor/test-model"


def test_directory_and_layered_registry_loading(tmp_path: Path) -> None:
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    (registry_dir / "custom.json").write_text(
        json.dumps(_registry_raw(endpoint_adapter={"developerRole": False})),
        encoding="utf-8",
    )

    registry = load_model_registry_from_directory(registry_dir)

    assert (
        registry.get_model("custom", "test-endpoint", "test-model").id == "test-model"
    )

    user_dir = tmp_path / "user"
    project_dir = tmp_path / "project"
    user_dir.mkdir()
    project_dir.mkdir()
    (user_dir / "provider.json").write_text(
        json.dumps(_registry_raw(endpoint_adapter={"developerRole": False})),
        encoding="utf-8",
    )
    (project_dir / "provider.json").write_text(
        json.dumps(
            _registry_raw(
                endpoint_adapter={"developerRole": False},
                model_extra={"displayName": "Project Override"},
            )
        ),
        encoding="utf-8",
    )

    layered = load_layered_model_registry(
        user_dir=user_dir,
        project_dir=project_dir,
    )

    assert (
        layered.get_model("custom", "test-endpoint", "test-model").name
        == "Project Override"
    )


def test_load_model_registry_dispatches_by_path_type(tmp_path: Path) -> None:
    path = _write_registry(
        tmp_path,
        _registry_raw(endpoint_adapter={"developerRole": False}),
    )
    directory = tmp_path / "models"
    directory.mkdir()
    (directory / "models.json").write_text(path.read_text(encoding="utf-8"))

    assert load_model_registry().list_models()
    assert (
        load_model_registry(path).get_model("custom", "test-endpoint", "test-model").id
        == "test-model"
    )
    assert (
        load_model_registry(directory)
        .get_model("custom", "test-endpoint", "test-model")
        .id
        == "test-model"
    )
    with pytest.raises(FileNotFoundError):
        load_model_registry(tmp_path / "missing.json")
