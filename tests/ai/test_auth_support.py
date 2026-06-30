from __future__ import annotations

from types import SimpleNamespace

import pytest

from loushang.ai.auth import (
    ApiKeyAuth,
    HeadersAuth,
    MissingAuthConfigError,
    MissingAuthError,
    NoAuth,
    OAuthBearerAuth,
)
from loushang.ai.auth.support import (
    AuthConfig,
    normalize_auth_kind,
    resolve_auth_for_model,
)
from loushang.ai.model import Auth, Endpoint, Model, ModelRegistry, Provider


def _model(auth: Auth | None = None):
    return SimpleNamespace(
        provider_id="demo",
        endpoint_id="responses",
        id="model-a",
        auth=auth,
    )


def test_auth_config_is_model_auth_type() -> None:
    assert AuthConfig is Auth


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("apiKey", "api_key"),
        ("api_key", "api_key"),
        ("api-key", "api_key"),
        ("oauth", "oauth"),
        ("none", "none"),
        (None, None),
    ],
)
def test_normalize_auth_kind(raw: str | None, expected: str | None) -> None:
    assert normalize_auth_kind(raw) == expected


def test_default_api_key_auth_reads_first_configured_env() -> None:
    view = resolve_auth_for_model(
        _model(Auth(api_key_envs=("MISSING_KEY", "DEMO_API_KEY"))),
        env={"DEMO_API_KEY": " env-secret "},
    )

    assert view.headers == {"Authorization": "Bearer env-secret"}


def test_default_api_key_auth_uses_header_prefix_and_extra_headers() -> None:
    view = resolve_auth_for_model(
        _model(
            Auth(
                api_key_env="DEMO_API_KEY",
                header="x-api-key",
                prefix="",
                extra_headers={"X-Static": "yes", "X-Env": "${DEMO_EXTRA}"},
            )
        ),
        env={"DEMO_API_KEY": "secret", "DEMO_EXTRA": "extra"},
    )

    assert view.headers == {
        "x-api-key": "secret",
        "X-Static": "yes",
        "X-Env": "extra",
    }


def test_default_api_key_auth_missing_env_raises_missing_auth() -> None:
    with pytest.raises(MissingAuthError) as exc_info:
        resolve_auth_for_model(
            _model(Auth(api_key_envs=("DEMO_API_KEY",))),
            env={},
        )

    payload = exc_info.value.to_dict()

    assert payload["code"] == "authentication"
    assert payload["details"] == {"expected_env": ["DEMO_API_KEY"]}


def test_default_oauth_auth_requires_explicit_bearer() -> None:
    with pytest.raises(MissingAuthError, match="OAuthBearerAuth"):
        resolve_auth_for_model(_model(Auth(kind="oauth")))


def test_default_none_auth_sends_no_headers() -> None:
    view = resolve_auth_for_model(_model(Auth(kind="none")))

    assert view.headers == {}


def test_missing_auth_config_raises_when_no_explicit_auth() -> None:
    with pytest.raises(MissingAuthConfigError):
        resolve_auth_for_model(_model(None))


def test_explicit_api_key_auth_wins_over_oauth_declaration_and_env() -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind="oauth", header="X-Auth", prefix="Token ")),
        options=SimpleNamespace(auth=ApiKeyAuth("explicit-secret")),
        env={"DEMO_API_KEY": "env-secret"},
    )

    assert view.headers == {"X-Auth": "Token explicit-secret"}


def test_explicit_oauth_bearer_auth_uses_declaration_header_prefix() -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind="oauth", header="X-OAuth", prefix="Bearer ")),
        options=SimpleNamespace(auth=OAuthBearerAuth("oauth-token")),
    )

    assert view.headers == {"X-OAuth": "Bearer oauth-token"}


def test_explicit_auth_can_override_header_prefix() -> None:
    view = resolve_auth_for_model(
        _model(Auth(header="Authorization", prefix="Bearer ")),
        options=SimpleNamespace(
            auth=ApiKeyAuth("explicit-secret", header="x-api-key", prefix="")
        ),
    )

    assert view.headers == {"x-api-key": "explicit-secret"}


def test_no_auth_explicitly_overrides_default_api_key() -> None:
    view = resolve_auth_for_model(
        _model(Auth(api_key_env="DEMO_API_KEY")),
        options=SimpleNamespace(auth=NoAuth()),
        env={"DEMO_API_KEY": "env-secret"},
    )

    assert view.headers == {}


def test_headers_auth_is_complete_explicit_header_override() -> None:
    view = resolve_auth_for_model(
        _model(Auth(extra_headers={"X-Default": "default"})),
        options=SimpleNamespace(
            auth=HeadersAuth(
                {
                    "Authorization": "Custom explicit-secret",
                    "X-Provider-Token": "provider-secret",
                }
            )
        ),
    )

    assert view.headers == {
        "Authorization": "Custom explicit-secret",
        "X-Provider-Token": "provider-secret",
    }


def test_resolver_does_not_use_env_or_stored_oauth_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "loushang.ai.auth.env.get_env_oauth_credentials",
        lambda *args, **kwargs: pytest.fail("env oauth lookup must not run"),
    )
    monkeypatch.setattr(
        "loushang.ai.auth.storage.load_credential_store",
        lambda *args, **kwargs: pytest.fail("stored oauth lookup must not run"),
    )

    with pytest.raises(MissingAuthError):
        resolve_auth_for_model(_model(Auth(kind="oauth")))


def test_auth_resolution_uses_model_effective_auth_without_registry_lookup() -> None:
    model = Model(
        id="ad-hoc",
        provider="demo",
        endpoint="responses",
        auth=Auth(header="X-API-Key", prefix="", api_key_env="DEMO_API_KEY"),
    )

    view = resolve_auth_for_model(
        model,
        options=SimpleNamespace(auth=ApiKeyAuth("secret")),
    )

    assert view.headers == {"X-API-Key": "secret"}


def test_loaded_model_holds_effective_provider_endpoint_auth() -> None:
    endpoint = Endpoint(
        id="responses",
        provider="demo",
        api="openai-responses",
        auth=Auth(extra_headers={"X-Endpoint": "endpoint"}),
        models={"ad-hoc": Model(id="ad-hoc", provider="demo", endpoint="responses")},
    )
    registry = ModelRegistry.from_providers(
        {
            "demo": Provider(
                id="demo",
                auth=Auth(header="X-Provider", prefix="Token "),
                endpoints={endpoint.id: endpoint},
            )
        }
    )
    model = registry.get_model("demo", "responses", "ad-hoc")

    view = resolve_auth_for_model(
        model,
        options=SimpleNamespace(auth=ApiKeyAuth("secret")),
    )

    assert view.headers == {
        "X-Provider": "Token secret",
        "X-Endpoint": "endpoint",
    }
