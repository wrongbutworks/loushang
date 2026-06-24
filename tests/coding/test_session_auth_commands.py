from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from loushang.ai.auth.registry import OAuthProviderRegistry
from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.model import Auth, Endpoint, Model, Provider
from loushang.ai.model.loader import load_model_registry_from_file
from loushang.ai.model.registry import ModelRegistry
from loushang.coding.session.agent_session import AgentSession
from loushang.coding.session.auth_commands import (
    SessionOAuthLoginCallbacks,
    login_scope_kwargs,
    resolve_auth_login_target,
    validate_oauth_login_target,
)


def _registry(
    *,
    provider_auth: Auth | None = None,
    endpoint_auth: Auth | None = None,
    model_auth: Auth | None = None,
) -> tuple[ModelRegistry, Model]:
    model = Model(id="chat", provider="demo", endpoint="responses", auth=model_auth)
    endpoint = Endpoint(
        id="responses",
        provider="demo",
        api="demo-api",
        auth=endpoint_auth,
        models={"chat": model},
    )
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=provider_auth,
                endpoints={"responses": endpoint},
            )
        }
    )
    return registry, registry.get_model("demo", "responses", "chat")


class _CustomOAuthProvider:
    id = "custom-oauth"
    name = "Custom OAuth"

    async def login(self, callbacks):
        raise AssertionError(f"unexpected login: {callbacks}")

    async def refresh_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        return credentials

    def get_api_key(self, credentials: OAuthCredentials) -> str:
        return credentials.access_token

    def uses_callback_server(self) -> bool:
        return False

    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]:
        del credentials
        return models


def test_current_model_login_uses_provider_scope_for_provider_auth() -> None:
    auth = Auth(kind="oauth")
    registry, model = _registry(provider_auth=auth)

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "provider"
    assert target.provider == "demo"
    assert login_scope_kwargs(target) == {"endpoint_id": None, "model_id": None}


def test_agent_session_login_uses_session_registry_and_preserves_registrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, model = _registry(
        provider_auth=Auth(kind="apiKey"),
        endpoint_auth=Auth(kind="oauth"),
    )
    oauth_registry = OAuthProviderRegistry()
    oauth_registry.register(_CustomOAuthProvider(), source_id="test")
    auth_records: list[Model] = []
    login_calls: list[dict[str, object]] = []

    async def _fake_oauth_login(
        provider_id,
        callbacks,
        *,
        registry,
        endpoint_id=None,
        model_id=None,
        persist=True,
    ):
        login_calls.append(
            {
                "provider_id": provider_id,
                "registry": registry,
                "endpoint_id": endpoint_id,
                "model_id": model_id,
                "persist": persist,
            }
        )
        callbacks.on_auth({"url": "https://example.test/login"})
        callbacks.on_progress("done")
        return OAuthCredentials(provider=provider_id, access_token="token")

    monkeypatch.setattr("loushang.ai.auth.oauth_login", _fake_oauth_login)
    session = AgentSession.__new__(AgentSession)
    session.agent = SimpleNamespace(model=model)
    session.model_registry = SimpleNamespace(ai_registry=registry)
    session.oauth_provider_registry = oauth_registry
    session._auth_bridge_controller = SimpleNamespace(
        record_model_auth_resolution=auth_records.append
    )

    result = asyncio.run(session._login_from_builtin(None))

    assert login_calls == [
        {
            "provider_id": "demo",
            "registry": oauth_registry,
            "endpoint_id": "responses",
            "model_id": None,
            "persist": True,
        }
    ]
    assert oauth_registry.get("custom-oauth") is not None
    assert oauth_registry.get("anthropic") is not None
    assert auth_records == [model]
    assert result["scope"] == "endpoint"
    assert result["auth_url"] == "https://example.test/login"
    assert result["progress"] == ["done"]


def test_current_model_login_uses_endpoint_scope_for_endpoint_auth() -> None:
    registry, model = _registry(
        provider_auth=Auth(kind="apiKey"),
        endpoint_auth=Auth(kind="oauth"),
    )

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "endpoint"
    assert target.endpoint_id == "responses"
    assert login_scope_kwargs(target) == {"endpoint_id": "responses", "model_id": None}


def test_current_model_login_uses_model_scope_for_model_auth() -> None:
    registry, model = _registry(
        provider_auth=Auth(kind="apiKey"),
        endpoint_auth=Auth(kind="apiKey"),
        model_auth=Auth(kind="oauth"),
    )

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "model"
    assert target.endpoint_id == "responses"
    assert target.model_id == "chat"
    assert login_scope_kwargs(target) == {"endpoint_id": "responses", "model_id": "chat"}


def test_explicit_login_target_uses_requested_scope() -> None:
    registry, model = _registry(provider_auth=Auth(kind="oauth"), endpoint_auth=Auth(kind="oauth"))

    provider_target = resolve_auth_login_target("demo", current_model=model, registry=registry)
    endpoint_target = resolve_auth_login_target("demo:responses", current_model=model, registry=registry)
    model_target = resolve_auth_login_target("demo:responses:chat", current_model=model, registry=registry)

    assert provider_target.scope == "provider"
    assert endpoint_target.scope == "endpoint"
    assert model_target.scope == "model"


def test_explicit_model_login_target_reports_missing_model() -> None:
    registry, model = _registry(provider_auth=Auth(kind="oauth"), endpoint_auth=Auth(kind="oauth"))

    with pytest.raises(ValueError, match="Model not found: demo:responses:missing"):
        resolve_auth_login_target("demo:responses:missing", current_model=model, registry=registry)


def test_validate_oauth_login_target_rejects_non_oauth_auth() -> None:
    registry, model = _registry(provider_auth=Auth(kind="apiKey"), endpoint_auth=Auth(kind="apiKey"))
    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    with pytest.raises(ValueError, match="OAuth login is not configured"):
        validate_oauth_login_target(target)


def test_oauth_callbacks_raise_actionable_manual_input_error() -> None:
    callbacks = SessionOAuthLoginCallbacks()
    callbacks.on_auth({"url": "https://example.test/login"})

    with pytest.raises(RuntimeError, match="https://example.test/login"):
        asyncio.run(callbacks.on_prompt({"message": "Paste the authorization code"}))


def test_loaded_provider_auth_defaults_to_provider_scope(tmp_path) -> None:
    registry = _loaded_registry(tmp_path, provider_auth={"kind": "oauth"})
    model = registry.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "provider"


def test_loaded_endpoint_auth_defaults_to_endpoint_scope(tmp_path) -> None:
    registry = _loaded_registry(
        tmp_path,
        provider_auth={"kind": "apiKey"},
        endpoint_auth={"kind": "oauth"},
    )
    model = registry.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "endpoint"
    assert target.endpoint_id == "responses"


def test_loaded_model_auth_defaults_to_model_scope(tmp_path) -> None:
    registry = _loaded_registry(
        tmp_path,
        provider_auth={"kind": "apiKey"},
        endpoint_auth={"kind": "apiKey"},
        model_auth={"kind": "oauth"},
    )
    model = registry.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "model"
    assert target.endpoint_id == "responses"
    assert target.model_id == "chat"


def test_loaded_endpoint_explicit_same_auth_still_uses_endpoint_scope(tmp_path) -> None:
    oauth_auth = {"kind": "oauth"}
    registry = _loaded_registry(
        tmp_path,
        provider_auth=oauth_auth,
        endpoint_auth=oauth_auth,
    )
    model = registry.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "endpoint"


def test_provider_raw_round_trip_keeps_inherited_auth_at_provider_scope(
    tmp_path,
) -> None:
    oauth_auth = {"kind": "oauth"}
    registry = _loaded_registry(tmp_path, provider_auth=oauth_auth)
    provider = registry.get_provider("demo")
    assert provider is not None
    raw = {"providers": {"demo": provider.to_raw()}}
    model_raw = raw["providers"]["demo"]["endpoints"]["responses"]["models"]["chat"]
    assert isinstance(model_raw, dict)
    assert "auth" not in model_raw
    path = tmp_path / "roundtrip.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    reloaded = load_model_registry_from_file(path)
    model = reloaded.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=reloaded)

    assert target.scope == "provider"


def test_provider_raw_round_trip_keeps_explicit_same_model_auth_scope(
    tmp_path,
) -> None:
    oauth_auth = {"kind": "oauth"}
    registry = _loaded_registry(
        tmp_path,
        provider_auth=oauth_auth,
        model_auth=oauth_auth,
    )
    provider = registry.get_provider("demo")
    assert provider is not None
    raw = {"providers": {"demo": provider.to_raw()}}
    model_raw = raw["providers"]["demo"]["endpoints"]["responses"]["models"]["chat"]
    assert isinstance(model_raw, dict)
    assert model_raw.get("auth") == {"kind": "oauth"}
    path = tmp_path / "roundtrip-model-auth.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    reloaded = load_model_registry_from_file(path)
    model = reloaded.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=reloaded)

    assert target.scope == "model"


def test_replace_providers_recomputes_explicit_auth_scope(tmp_path) -> None:
    oauth_auth = {"kind": "oauth"}
    registry = _loaded_registry(
        tmp_path,
        provider_auth=oauth_auth,
        endpoint_auth=oauth_auth,
    )
    replacement = Provider(
        id="demo",
        auth=Auth(kind="oauth"),
        endpoints={
            "responses": Endpoint(
                id="responses",
                provider="demo",
                api="demo-api",
                models={"chat": Model(id="chat", provider="demo", endpoint="responses")},
            )
        },
    )

    registry.replace_providers({"demo": replacement})
    model = registry.get_model("demo", "responses", "chat")
    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "provider"


def test_programmatic_model_auth_same_as_provider_keeps_model_scope() -> None:
    auth = Auth(kind="oauth")
    registry = ModelRegistry()
    registry.register_provider(
        Provider(
            id="demo",
            auth=auth,
            endpoints={
                "responses": Endpoint(
                    id="responses",
                    provider="demo",
                    api="demo-api",
                    models={
                        "chat": Model(
                            id="chat",
                            provider="demo",
                            endpoint="responses",
                            auth=auth,
                        )
                    },
                )
            },
        )
    )
    model = registry.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "model"


def test_incremental_register_model_auth_same_as_provider_keeps_model_scope() -> None:
    auth = Auth(kind="oauth")
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=auth,
                endpoints={
                    "responses": Endpoint(
                        id="responses",
                        provider="demo",
                        api="demo-api",
                    )
                },
            )
        }
    )

    registry.register_model(
        Model(
            id="chat",
            provider="demo",
            endpoint="responses",
            auth=auth,
        )
    )
    model = registry.get_model("demo", "responses", "chat")
    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "model"


def test_reregister_normalized_endpoint_preserves_model_auth_scope() -> None:
    auth = Auth(kind="oauth")
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=auth,
                endpoints={
                    "responses": Endpoint(
                        id="responses",
                        provider="demo",
                        api="demo-api",
                        models={
                            "chat": Model(
                                id="chat",
                                provider="demo",
                                endpoint="responses",
                                auth=auth,
                            )
                        },
                    )
                },
            )
        }
    )
    endpoint = registry.get_endpoint("demo", "responses")
    assert endpoint is not None

    registry.register_endpoint("demo", endpoint)
    model = registry.get_model("demo", "responses", "chat")
    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "model"


def test_reregister_endpoint_can_clear_model_auth_scope() -> None:
    auth = Auth(kind="oauth")
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=auth,
                endpoints={
                    "responses": Endpoint(
                        id="responses",
                        provider="demo",
                        api="demo-api",
                        models={
                            "chat": Model(
                                id="chat",
                                provider="demo",
                                endpoint="responses",
                                auth=auth,
                            )
                        },
                    )
                },
            )
        }
    )
    endpoint = registry.get_endpoint("demo", "responses")
    assert endpoint is not None
    model = endpoint.get_model("chat")
    assert model is not None

    registry.register_endpoint(
        "demo",
        Endpoint(
            id=endpoint.id,
            provider=endpoint.provider_id,
            api=endpoint.api,
            models={"chat": Model(id=model.id, provider="demo", endpoint="responses")},
        ),
    )
    resolved_model = registry.get_model("demo", "responses", "chat")
    target = resolve_auth_login_target(
        None,
        current_model=resolved_model,
        registry=registry,
    )

    assert target.scope == "provider"


def test_programmatic_endpoint_auth_same_as_provider_keeps_endpoint_scope() -> None:
    auth = Auth(kind="oauth")
    registry = ModelRegistry()
    registry.register_provider(
        Provider(
            id="demo",
            auth=auth,
            endpoints={
                "responses": Endpoint(
                    id="responses",
                    provider="demo",
                    api="demo-api",
                    auth=auth,
                    models={
                        "chat": Model(id="chat", provider="demo", endpoint="responses")
                    },
                )
            },
        )
    )
    model = registry.get_model("demo", "responses", "chat")

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "endpoint"


def _loaded_registry(
    tmp_path,
    *,
    provider_auth: dict[str, object] | None = None,
    endpoint_auth: dict[str, object] | None = None,
    model_auth: dict[str, object] | None = None,
) -> ModelRegistry:
    model_raw: dict[str, object] = {
        "displayName": "Chat",
        "capabilities": {
            "input": ["text"],
            "output": ["text"],
        },
    }
    if model_auth is not None:
        model_raw["auth"] = model_auth
    endpoint_raw: dict[str, object] = {
        "api": "demo-api",
        "models": {"chat": model_raw},
    }
    if endpoint_auth is not None:
        endpoint_raw["auth"] = endpoint_auth
    provider_raw: dict[str, object] = {
        "endpoints": {"responses": endpoint_raw},
    }
    if provider_auth is not None:
        provider_raw["auth"] = provider_auth
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"providers": {"demo": provider_raw}}), encoding="utf-8")
    return load_model_registry_from_file(path)
