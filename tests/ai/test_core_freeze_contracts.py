from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import loushang.ai as ai
from loushang.ai.api_registry import ApiProviderRegistry
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


def _custom_registry_raw(
    provider_id: str = "company-aif002",
    *,
    stream: bool = False,
) -> dict[str, object]:
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
                                    "stream": stream,
                                },
                            }
                        },
                    }
                },
            }
        }
    }


def _write_custom_registry(
    path: Path,
    provider_id: str = "company-aif002",
    *,
    stream: bool = False,
) -> None:
    path.write_text(
        json.dumps(_custom_registry_raw(provider_id, stream=stream), indent=2),
        encoding="utf-8",
    )


class _RecordingProvider:
    api = "anthropic-messages"

    def __init__(self) -> None:
        self.modes: list[str | None] = []

    def stream_raw(self, request):
        return self._raw_parts(request)

    def invoke_raw(self, request):
        return self._raw_parts(request)

    async def _raw_parts(self, request):
        self.modes.append(getattr(request, "mode", None))
        yield {"type": "response_start", "response_id": "aif002"}
        yield {"type": "text_delta", "text": "ok"}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


class _InvokeRawOnlyProvider:
    api = "anthropic-messages"

    def __init__(self) -> None:
        self.modes: list[str | None] = []

    def invoke_raw(self, request):
        return self._raw_parts(request)

    async def _raw_parts(self, request):
        self.modes.append(getattr(request, "mode", None))
        yield {"type": "response_start", "response_id": "aif002"}
        yield {"type": "text_delta", "text": "ok"}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


class _StreamRawOnlyProvider:
    api = "anthropic-messages"

    def stream_raw(self, request):
        raise AssertionError("not used by this contract test")


def test_no_legacy_compat_model_contract_types_remain() -> None:
    import loushang.ai.model as model_module

    removed_public = "Com" + "pat"
    removed_schema = "compat" + "_schema"

    assert removed_public not in model_module.__all__
    assert not hasattr(model_module, removed_public)
    assert not (MODEL_DIR / f"{removed_schema}.py").exists()

    forbidden_source_tokens = (
        "class " + removed_public,
        "LEGACY_COMPAT_TRANSLATION_TARGETS",
        "resolve_anthropic_messages_compat",
        "resolve_openai_completions_compat",
        "resolve_openai_responses_compat",
        removed_schema,
    )
    for path in (MODEL_DIR).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_source_tokens:
            assert token not in text, (path, token)


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


def test_deprecated_provider_specific_options_are_not_core_api() -> None:
    import loushang.ai.api as api_module
    import loushang.ai.options as options_module

    forbidden = {
        "AnthropicOptions",
        "OpenAICompletionsOptions",
        "OpenAIResponsesOptions",
    }
    public_modules = (ai, api_module, options_module)
    for module in public_modules:
        for name in forbidden:
            assert not hasattr(module, name), (module.__name__, name)

    for path in (REPO_ROOT / "examples/ai").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in text, (path, name)


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


def test_default_registry_fails_on_bad_user_model_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_model_dir = tmp_path / ".loushang" / "models"
    user_model_dir.mkdir(parents=True)
    (user_model_dir / "bad.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    clear_default_model_registry()

    try:
        with pytest.raises((json.JSONDecodeError, ValueError)):
            get_default_model_registry()
    finally:
        clear_default_model_registry()


@pytest.mark.xfail(
    strict=True,
    reason="AIF-008 renames provider raw invocation from stream_raw to invoke_raw",
)
def test_provider_registry_accepts_invoke_raw_and_rejects_stream_raw() -> None:
    registry = ApiProviderRegistry()

    registry.register_api_provider(_InvokeRawOnlyProvider())
    with pytest.raises(TypeError):
        registry.register_api_provider(_StreamRawOnlyProvider())


@pytest.mark.xfail(
    strict=True,
    reason="AIF-008 dispatches provider raw calls through invoke_raw",
)
def test_complete_dispatches_to_invoke_raw_provider(tmp_path: Path) -> None:
    async def run() -> None:
        path = tmp_path / "company.json"
        _write_custom_registry(path, stream=True)
        model = load_model_registry_from_file(path).get_model(
            "company-aif002",
            "anthropic-messages",
            "company-chat",
        )
        provider = _InvokeRawOnlyProvider()
        provider_registry = ApiProviderRegistry()
        provider_registry.register_api_provider(provider)

        message = await ai.complete(
            model,
            {"messages": [{"role": "user", "content": "hello"}]},
            CallOptions(api_key="test-key"),
            registry=provider_registry,
        )

        assert message.text == "ok"
        assert provider.modes == ["complete"]

    asyncio.run(run())


@pytest.mark.xfail(
    strict=True,
    reason="AIF-008 dispatches streaming provider raw calls through invoke_raw",
)
def test_stream_dispatches_to_invoke_raw_provider(tmp_path: Path) -> None:
    async def run() -> None:
        path = tmp_path / "company.json"
        _write_custom_registry(path, stream=True)
        model = load_model_registry_from_file(path).get_model(
            "company-aif002",
            "anthropic-messages",
            "company-chat",
        )
        provider = _InvokeRawOnlyProvider()
        provider_registry = ApiProviderRegistry()
        provider_registry.register_api_provider(provider)

        event_stream = await ai.stream(
            model,
            {"messages": [{"role": "user", "content": "hello"}]},
            CallOptions(api_key="test-key"),
            registry=provider_registry,
        )
        async for _event in event_stream:
            pass

        assert provider.modes == ["stream"]

    asyncio.run(run())


@pytest.mark.xfail(
    strict=True,
    reason="AIF-008 passes ProviderRequest.mode through complete() and stream()",
)
def test_complete_and_stream_pass_distinct_provider_modes(tmp_path: Path) -> None:
    async def run() -> None:
        path = tmp_path / "company.json"
        _write_custom_registry(path, stream=True)
        model = load_model_registry_from_file(path).get_model(
            "company-aif002",
            "anthropic-messages",
            "company-chat",
        )
        provider = _RecordingProvider()
        provider_registry = ApiProviderRegistry()
        provider_registry.register_api_provider(provider)
        context = {"messages": [{"role": "user", "content": "hello"}]}

        await ai.complete(
            model,
            context,
            CallOptions(api_key="test-key"),
            registry=provider_registry,
        )
        event_stream = await ai.stream(
            model,
            context,
            CallOptions(api_key="test-key"),
            registry=provider_registry,
        )
        async for _event in event_stream:
            pass

        assert provider.modes == ["complete", "stream"]

    asyncio.run(run())


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
