from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

import loushang.ai.auth as auth
from loushang.ai import ApiKeyAuth, OAuthBearerAuth, OAuthCredential
from loushang.ai.model import Auth, Model, OAuthConfig


def _model(declaration: Auth) -> Model:
    return Model(
        id="auth-api-model",
        provider="example",
        endpoint="oauth",
        api="openai-responses",
        base_url="https://model.test/v1",
        auth=declaration,
    )


def _generic_oauth() -> Auth:
    return Auth(
        kind="oauth",
        provider="example-oauth",
        oauth=OAuthConfig(
            client_id="example-client",
            authorization_endpoint="https://oauth.test/authorize",
            token_endpoint="https://oauth.test/token",
            scopes=("model.invoke",),
        ),
    )


@dataclass
class _ExternalSource:
    credential: OAuthCredential | None = None
    id: str = "external-oauth"
    description: str = "Use external application login"
    experimental: bool = True
    supports_refresh: bool = False

    def matches(self, model: object) -> bool:
        declaration = getattr(model, "auth", None)
        return getattr(declaration, "provider", None) == self.id

    def load(self) -> OAuthCredential | None:
        return self.credential

    def load_file(self, path: str | Path) -> OAuthCredential:
        del path
        if self.credential is None:
            raise RuntimeError("fixture credential is missing")
        return self.credential


def test_get_auth_and_status_resolve_api_key_without_login() -> None:
    model = _model(Auth(kind="apiKey", api_key_env="EXAMPLE_KEY"))

    async def scenario():
        request_auth = await auth.get_auth(model, env={"EXAMPLE_KEY": "secret"})
        current = await auth.status(model, env={"EXAMPLE_KEY": "secret"})
        missing = await auth.status(model, env={})
        return request_auth, current, missing

    request_auth, current, missing = asyncio.run(scenario())

    assert request_auth == ApiKeyAuth("secret")
    assert current.authenticated is True
    assert current.auth_kind == "api_key"
    assert current.actions == ()
    assert missing.authenticated is False
    assert missing.actions == ("configure_api_key",)


def test_get_auth_missing_oauth_is_structured_and_never_starts_login() -> None:
    model = _model(_generic_oauth())

    with pytest.raises(auth.AuthenticationRequiredError) as exc_info:
        asyncio.run(auth.get_auth(model, extensions=auth.AuthExtensionRegistry()))

    assert exc_info.value.info.details["reason"] == "missing_credential"
    assert exc_info.value.info.details["available_actions"] == ["login"]


def test_login_returns_session_without_opening_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _model(_generic_oauth())

    def fail_if_opened(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise AssertionError("auth.login must not open a browser")

    monkeypatch.setattr("webbrowser.open", fail_if_opened)

    async def scenario():
        session = await auth.login(model)
        try:
            assert session.authorization_url.startswith("https://oauth.test/authorize?")
            assert session.redirect_uri.startswith("http://127.0.0.1:")
            return session
        finally:
            await session.close()

    session = asyncio.run(scenario())
    assert isinstance(session, auth.OAuthLoginSession)


def test_status_and_get_auth_use_extension_registry_metadata() -> None:
    credential = OAuthCredential(
        provider="external-oauth",
        access_token="external-access",
        expires_at=4102444800,
    )
    source = _ExternalSource(credential=credential)
    registry = auth.AuthExtensionRegistry([source])
    model = _model(Auth(kind="oauth", provider=source.id))

    async def scenario():
        current = await auth.status(model, extensions=registry)
        request_auth = await auth.get_auth(model, extensions=registry)
        source.credential = None
        missing = await auth.status(model, extensions=registry)
        return current, request_auth, missing

    current, request_auth, missing = asyncio.run(scenario())

    assert current.authenticated is True
    assert current.experimental is True
    assert current.source_description == source.description
    assert request_auth == OAuthBearerAuth("external-access")
    assert missing.authenticated is False
    assert missing.actions == ("external_credential",)
    assert missing.to_dict()["actions"] == ["external_credential"]


def test_source_only_model_cannot_be_treated_as_generic_login() -> None:
    model = _model(Auth(kind="oauth", provider="openai-codex"))

    with pytest.raises(auth.AuthenticationRequiredError) as exc_info:
        asyncio.run(auth.login(model))

    assert exc_info.value.info.details == {
        "reason": "login_unavailable",
        "available_actions": ["external_credential"],
    }
