from __future__ import annotations

import asyncio
import json

import pytest

from loushang.ai.model import Auth, Endpoint, Model, Provider
from loushang.ai.model.loader import load_model_registry_from_file
from loushang.ai.model.registry import ModelRegistry
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


def test_current_model_login_uses_provider_scope_for_provider_auth() -> None:
    auth = Auth(kind="oauth")
    registry, model = _registry(provider_auth=auth, endpoint_auth=auth)
    endpoint = registry.get_endpoint("demo", "responses")
    assert endpoint is not None
    object.__setattr__(endpoint, "_auth_inherited", True)

    target = resolve_auth_login_target(None, current_model=model, registry=registry)

    assert target.scope == "provider"
    assert target.provider == "demo"
    assert login_scope_kwargs(target) == {"endpoint_id": None, "model_id": None}


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
