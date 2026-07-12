from __future__ import annotations

from types import SimpleNamespace

import pytest

from loushang.ai import ApiKeyAuth, CallOptions, HeadersAuth, OAuthBearerAuth
from loushang.ai.auth import (
    AuthResolutionError,
    InvalidAuthConfigError,
    MissingAuthConfigError,
    MissingAuthError,
)
from loushang.ai.auth.support import (
    AuthConfig,
    normalize_auth_kind,
    resolve_auth_for_model,
    resolve_explicit_auth,
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


def test_typed_call_options_auth_uses_catalog_header() -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind="oauth", header="X-Auth", prefix="Token ")),
        options=CallOptions(auth=OAuthBearerAuth("oauth-token")),
    )

    assert view.headers == {"X-Auth": "Token oauth-token"}


def test_positional_explicit_auth_remains_supported() -> None:
    view = resolve_explicit_auth(
        OAuthBearerAuth("legacy-oauth"),
        declaration_hint=Auth(kind="oauth"),
    )

    assert view.headers == {"Authorization": "Bearer legacy-oauth"}


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


def test_default_api_key_auth_prefers_primary_env_before_fallbacks() -> None:
    view = resolve_auth_for_model(
        _model(
            Auth(
                api_key_env="PRIMARY_KEY",
                api_key_envs=("FALLBACK_KEY",),
            )
        ),
        env={"PRIMARY_KEY": "primary", "FALLBACK_KEY": "fallback"},
    )

    assert view.headers == {"Authorization": "Bearer primary"}


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


def test_default_api_key_auth_rejects_catalog_primary_header_override() -> None:
    with pytest.raises(InvalidAuthConfigError) as exc_info:
        resolve_auth_for_model(
            _model(
                Auth(
                    api_key_env="DEMO_API_KEY",
                    extra_headers={"authorization": "Bearer override-secret"},
                )
            ),
            env={"DEMO_API_KEY": "env-secret"},
        )

    assert exc_info.value.to_dict()["details"] == {
        "conflicting_header": "authorization",
        "primary_header": "Authorization",
    }
    assert "override-secret" not in str(exc_info.value.to_dict())


@pytest.mark.parametrize(
    "extra_headers",
    [
        {"Bad Header": "value"},
        {"X-Extra": "value\r\nX-Evil: yes"},
        {"X-Extra": "one", "x-extra": "two"},
    ],
)
def test_catalog_extra_header_validation_uses_configuration_errors(
    extra_headers: dict[str, str],
) -> None:
    with pytest.raises(InvalidAuthConfigError):
        resolve_auth_for_model(
            _model(
                Auth(
                    api_key_env="DEMO_API_KEY",
                    extra_headers=extra_headers,
                )
            ),
            env={"DEMO_API_KEY": "secret"},
        )


def test_default_api_key_auth_missing_env_raises_missing_auth() -> None:
    with pytest.raises(MissingAuthError) as exc_info:
        resolve_auth_for_model(
            _model(Auth(api_key_envs=("DEMO_API_KEY",))),
            env={},
        )

    assert exc_info.value.to_dict()["details"] == {"expected_env": ["DEMO_API_KEY"]}


def test_default_api_key_auth_rejects_injected_environment_secret() -> None:
    with pytest.raises(AuthResolutionError, match="CR or LF"):
        resolve_auth_for_model(
            _model(Auth(api_key_env="DEMO_API_KEY")),
            env={"DEMO_API_KEY": "secret\r\nX-Evil: yes"},
        )


def test_explicit_empty_header_name_does_not_fall_back() -> None:
    with pytest.raises(AuthResolutionError, match="invalid HTTP header name"):
        resolve_auth_for_model(
            _model(Auth()),
            options=CallOptions(auth=ApiKeyAuth("secret", header="")),
        )


def test_default_oauth_auth_requires_explicit_credentials() -> None:
    with pytest.raises(MissingAuthError, match="OAuthBearerAuth"):
        resolve_auth_for_model(_model(Auth(kind="oauth")))


def test_default_none_auth_returns_no_headers() -> None:
    view = resolve_auth_for_model(_model(Auth(kind="none")))

    assert view.headers == {}


def test_missing_auth_config_raises_when_no_explicit_auth() -> None:
    with pytest.raises(MissingAuthConfigError):
        resolve_auth_for_model(_model(None))


def test_explicit_api_key_uses_catalog_header_and_extra_headers() -> None:
    view = resolve_auth_for_model(
        _model(
            Auth(
                header="X-API-Key",
                prefix="Token ",
                extra_headers={"X-Catalog": "catalog"},
            )
        ),
        options=CallOptions(auth=ApiKeyAuth("explicit-secret")),
    )

    assert view.headers == {
        "X-API-Key": "Token explicit-secret",
        "X-Catalog": "catalog",
    }


def test_explicit_auth_extra_headers_use_the_injected_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_EXTRA", "from-process")

    view = resolve_auth_for_model(
        _model(Auth(extra_headers={"X-Extra": "${DEMO_EXTRA}"})),
        options=CallOptions(auth=ApiKeyAuth("explicit-secret")),
        env={"DEMO_EXTRA": "from-injected"},
    )

    assert view.headers == {
        "Authorization": "Bearer explicit-secret",
        "X-Extra": "from-injected",
    }


def test_explicit_auth_does_not_fall_back_to_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_EXTRA", "from-process")

    with pytest.raises(InvalidAuthConfigError, match="missing environment"):
        resolve_auth_for_model(
            _model(Auth(extra_headers={"X-Extra": "${DEMO_EXTRA}"})),
            options=CallOptions(auth=ApiKeyAuth("explicit-secret")),
            env={},
        )


def test_typed_api_key_uses_catalog_header() -> None:
    view = resolve_auth_for_model(
        _model(Auth(header="X-API-Key", prefix="Token ")),
        options=CallOptions(auth=ApiKeyAuth("typed-secret")),
    )

    assert view.headers == {
        "X-API-Key": "Token typed-secret",
    }


@pytest.mark.parametrize(
    ("kind", "normalized_kind"),
    [("oauth", "oauth"), ("none", "none"), ("custom", "custom")],
)
def test_explicit_api_key_overrides_catalog_kind(
    kind: str,
    normalized_kind: str,
) -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind=kind)),
        options=CallOptions(auth=ApiKeyAuth("explicit-secret")),
    )

    assert normalized_kind
    assert view.headers == {"Authorization": "Bearer explicit-secret"}


def test_explicit_oauth_uses_catalog_header_and_extra_headers() -> None:
    view = resolve_auth_for_model(
        _model(
            Auth(
                kind="oauth",
                header="X-OAuth",
                prefix="Bearer ",
                extra_headers={"originator": "loushang"},
            )
        ),
        options=CallOptions(auth=OAuthBearerAuth("oauth-token")),
    )

    assert view.headers == {
        "X-OAuth": "Bearer oauth-token",
        "originator": "loushang",
    }


def test_explicit_oauth_rejects_blank_access_token() -> None:
    with pytest.raises(AuthResolutionError, match="auth.access_token"):
        resolve_auth_for_model(
            _model(Auth(kind="oauth")),
            options=CallOptions(auth=OAuthBearerAuth("  ")),
        )


def test_chatgpt_route_combines_bearer_catalog_and_account_headers() -> None:
    from loushang.ai import get_model

    model = get_model(
        "openai",
        "openai-responses-chatgpt",
        "gpt-5.5-chatgpt",
    )

    view = resolve_auth_for_model(
        model,
        options=CallOptions(
            auth=HeadersAuth(
                {
                    "Authorization": "Bearer chatgpt-token",
                    "originator": "loushang",
                    "OpenAI-Beta": "responses=experimental",
                    "chatgpt-account-id": "account-1",
                }
            )
        ),
    )

    assert view.headers == {
        "Authorization": "Bearer chatgpt-token",
        "originator": "loushang",
        "OpenAI-Beta": "responses=experimental",
        "chatgpt-account-id": "account-1",
    }


def test_headers_auth_is_an_authoritative_override() -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind="oauth")),
        options=CallOptions(auth=HeadersAuth({"X-Custom-Auth": "token"})),
    )

    assert view.headers == {"X-Custom-Auth": "token"}


def test_headers_auth_rejects_case_insensitive_duplicates() -> None:
    with pytest.raises(AuthResolutionError, match="duplicate case-insensitive"):
        resolve_auth_for_model(
            _model(Auth(kind="oauth")),
            options=CallOptions(
                auth=HeadersAuth(
                    {
                        "Authorization": "Bearer good",
                        "authorization": "Bearer bad",
                    }
                )
            ),
        )


def test_headers_auth_rejects_empty_headers() -> None:
    with pytest.raises(AuthResolutionError, match="use NoAuth"):
        resolve_auth_for_model(
            _model(Auth(kind="oauth")),
            options=CallOptions(auth=HeadersAuth({})),
        )


@pytest.mark.parametrize(
    "auth",
    [ApiKeyAuth("secret\r\ninjected"), OAuthBearerAuth("secret\nvalue")],
)
def test_explicit_secret_rejects_header_injection(auth) -> None:
    with pytest.raises(AuthResolutionError, match="CR or LF"):
        resolve_auth_for_model(_model(Auth()), options=CallOptions(auth=auth))


@pytest.mark.parametrize(
    "auth",
    [
        ApiKeyAuth("secret", header=123),  # type: ignore[arg-type]
        ApiKeyAuth("secret", prefix=123),  # type: ignore[arg-type]
        OAuthBearerAuth("secret", header=123),  # type: ignore[arg-type]
        OAuthBearerAuth("secret", prefix=123),  # type: ignore[arg-type]
    ],
)
def test_explicit_auth_rejects_non_string_header_and_prefix(auth) -> None:
    with pytest.raises(AuthResolutionError):
        resolve_auth_for_model(_model(Auth()), options=CallOptions(auth=auth))


@pytest.mark.parametrize(
    "headers",
    [
        {"Bad Header": "value"},
        {"Authorization:": "value"},
        {"Authorization": "Bearer secret\r\nX-Evil: yes"},
    ],
)
def test_headers_auth_rejects_invalid_http_headers(headers) -> None:
    with pytest.raises(AuthResolutionError):
        resolve_auth_for_model(
            _model(Auth(kind="oauth")),
            options=CallOptions(auth=HeadersAuth(headers)),
        )


def test_missing_extra_header_environment_reference_fails_fast() -> None:
    with pytest.raises(InvalidAuthConfigError) as exc_info:
        resolve_auth_for_model(
            _model(
                Auth(
                    api_key_env="DEMO_API_KEY",
                    extra_headers={"X-Required": "${MISSING_HEADER}"},
                )
            ),
            env={"DEMO_API_KEY": "secret"},
        )

    assert exc_info.value.to_dict()["details"] == {
        "expected_env": "MISSING_HEADER",
        "header": "X-Required",
    }


def test_headers_auth_and_auth_view_defensively_copy_input() -> None:
    source = {"Authorization": "Bearer original"}
    auth = HeadersAuth(source)
    source["Authorization"] = "Bearer mutated"

    view = resolve_auth_for_model(
        _model(Auth(kind="oauth")), options=CallOptions(auth=auth)
    )

    assert view.headers == {"Authorization": "Bearer original"}
    assert "original" not in repr(auth)
    assert "original" not in repr(view)


def test_no_auth_explicitly_overrides_catalog_auth() -> None:
    from loushang.ai import NoAuth

    view = resolve_auth_for_model(
        _model(Auth(kind="oauth")),
        options=CallOptions(auth=NoAuth()),
    )

    assert view.headers == {}


@pytest.mark.parametrize(
    ("kind", "normalized_kind"),
    [("apiKey", "api_key"), ("none", "none"), ("custom", "custom")],
)
def test_explicit_oauth_overrides_catalog_kind(
    kind: str,
    normalized_kind: str,
) -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind=kind)),
        options=CallOptions(auth=OAuthBearerAuth("oauth-token")),
    )

    assert normalized_kind
    assert view.headers == {"Authorization": "Bearer oauth-token"}


def test_explicit_oauth_is_allowed_without_declaration_for_direct_model() -> None:
    view = resolve_auth_for_model(
        _model(None),
        options=CallOptions(auth=OAuthBearerAuth("oauth-token")),
    )

    assert view.headers == {"Authorization": "Bearer oauth-token"}


def test_explicit_api_key_is_allowed_without_declaration_for_direct_model() -> None:
    view = resolve_auth_for_model(
        _model(None),
        options=CallOptions(auth=ApiKeyAuth("explicit-secret")),
    )

    assert view.headers == {"Authorization": "Bearer explicit-secret"}


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

    view = resolve_auth_for_model(model, options=CallOptions(auth=ApiKeyAuth("secret")))

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

    view = resolve_auth_for_model(model, options=CallOptions(auth=ApiKeyAuth("secret")))

    assert view.headers == {
        "X-Provider": "Token secret",
        "X-Endpoint": "endpoint",
    }
