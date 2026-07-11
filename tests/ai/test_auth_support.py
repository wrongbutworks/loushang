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


def test_default_api_key_auth_missing_env_raises_missing_auth() -> None:
    with pytest.raises(MissingAuthError) as exc_info:
        resolve_auth_for_model(
            _model(Auth(api_key_envs=("DEMO_API_KEY",))),
            env={},
        )

    assert exc_info.value.to_dict()["details"] == {"expected_env": ["DEMO_API_KEY"]}


def test_default_oauth_auth_requires_explicit_credentials() -> None:
    with pytest.raises(MissingAuthError, match="OAuthBearerAuth"):
        resolve_auth_for_model(_model(Auth(kind="oauth")))


def test_default_none_auth_merges_only_non_auth_headers() -> None:
    view = resolve_auth_for_model(
        _model(Auth(kind="none")),
        options=CallOptions(headers={"X-Trace": "trace"}),
    )

    assert view.headers == {"X-Trace": "trace"}


def test_missing_auth_config_raises_when_no_explicit_auth() -> None:
    with pytest.raises(MissingAuthConfigError):
        resolve_auth_for_model(_model(None))


def test_explicit_api_key_uses_catalog_header_and_merges_extra_headers() -> None:
    view = resolve_auth_for_model(
        _model(
            Auth(
                header="X-API-Key",
                prefix="Token ",
                extra_headers={"X-Catalog": "catalog"},
            )
        ),
        options=CallOptions(
            api_key="explicit-secret",
            headers={"X-Trace": "trace"},
        ),
    )

    assert view.headers == {
        "X-API-Key": "Token explicit-secret",
        "X-Catalog": "catalog",
        "X-Trace": "trace",
    }


def test_typed_api_key_uses_catalog_header_and_caller_headers() -> None:
    view = resolve_auth_for_model(
        _model(Auth(header="X-API-Key", prefix="Token ")),
        options=CallOptions(
            auth=ApiKeyAuth("typed-secret"),
            headers={"X-Trace": "trace"},
        ),
    )

    assert view.headers == {
        "X-API-Key": "Token typed-secret",
        "X-Trace": "trace",
    }


@pytest.mark.parametrize(
    ("kind", "normalized_kind"),
    [("oauth", "oauth"), ("none", "none"), ("custom", "custom")],
)
def test_explicit_api_key_requires_api_key_declaration(
    kind: str,
    normalized_kind: str,
) -> None:
    with pytest.raises(AuthResolutionError, match="cannot satisfy") as exc_info:
        resolve_auth_for_model(
            _model(Auth(kind=kind)),
            options=CallOptions(api_key="explicit-secret"),
        )

    assert exc_info.value.to_dict()["details"] == {
        "auth_kind": normalized_kind,
        "provided_kind": "api_key",
    }


def test_explicit_oauth_uses_catalog_header_and_merges_caller_headers() -> None:
    view = resolve_auth_for_model(
        _model(
            Auth(
                kind="oauth",
                header="X-OAuth",
                prefix="Bearer ",
                extra_headers={"originator": "loushang"},
            )
        ),
        options=CallOptions(
            auth=OAuthBearerAuth("oauth-token"),
            headers={
                "chatgpt-account-id": "account-1",
                "X-Trace": "trace",
            },
        ),
    )

    assert view.headers == {
        "X-OAuth": "Bearer oauth-token",
        "originator": "loushang",
        "chatgpt-account-id": "account-1",
        "X-Trace": "trace",
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
            auth=OAuthBearerAuth("chatgpt-token"),
            headers={"chatgpt-account-id": "account-1"},
        ),
    )

    assert view.headers == {
        "Authorization": "Bearer chatgpt-token",
        "originator": "loushang",
        "OpenAI-Beta": "responses=experimental",
        "chatgpt-account-id": "account-1",
    }


def test_headers_auth_is_authoritative_and_cannot_add_supplemental_headers() -> None:
    with pytest.raises(AuthResolutionError, match="cannot be combined"):
        resolve_auth_for_model(
            _model(Auth(kind="oauth")),
            options=CallOptions(
                auth=HeadersAuth({"Authorization": "Bearer token"}),
                headers={"X-Trace": "trace"},
            ),
        )


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
def test_explicit_oauth_requires_oauth_declaration(
    kind: str,
    normalized_kind: str,
) -> None:
    with pytest.raises(AuthResolutionError, match="cannot satisfy") as exc_info:
        resolve_auth_for_model(
            _model(Auth(kind=kind)),
            options=CallOptions(auth=OAuthBearerAuth("oauth-token")),
        )

    assert exc_info.value.to_dict()["details"] == {
        "auth_kind": normalized_kind,
        "provided_kind": "oauth",
    }


def test_explicit_oauth_is_allowed_without_declaration_for_direct_model() -> None:
    view = resolve_auth_for_model(
        _model(None),
        options=CallOptions(auth=OAuthBearerAuth("oauth-token")),
    )

    assert view.headers == {"Authorization": "Bearer oauth-token"}


def test_explicit_api_key_is_allowed_without_declaration_for_direct_model() -> None:
    view = resolve_auth_for_model(
        _model(None),
        options=CallOptions(api_key="explicit-secret"),
    )

    assert view.headers == {"Authorization": "Bearer explicit-secret"}


@pytest.mark.parametrize(
    ("options", "auth", "conflicting_header", "source"),
    [
        (
            CallOptions(api_key="secret", headers={"authorization": "override"}),
            Auth(),
            "authorization",
            "CallOptions.headers",
        ),
        (
            CallOptions(
                auth=OAuthBearerAuth("oauth-token"),
                headers={"AUTHORIZATION": "override"},
            ),
            Auth(kind="oauth"),
            "AUTHORIZATION",
            "CallOptions.headers",
        ),
    ],
)
def test_caller_headers_cannot_override_primary_auth_header(
    options: CallOptions,
    auth: Auth,
    conflicting_header: str,
    source: str,
) -> None:
    with pytest.raises(InvalidAuthConfigError) as exc_info:
        resolve_auth_for_model(_model(auth), options=options)

    assert exc_info.value.to_dict()["details"] == {
        "conflicting_header": conflicting_header,
        "primary_header": "Authorization",
        "source": source,
    }


def test_resolver_does_not_use_env_or_stored_oauth_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "loushang.auth.env.get_env_oauth_credentials",
        lambda *args, **kwargs: pytest.fail("env oauth lookup must not run"),
    )
    monkeypatch.setattr(
        "loushang.auth.storage.load_credential_store",
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

    view = resolve_auth_for_model(model, options=CallOptions(api_key="secret"))

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

    view = resolve_auth_for_model(model, options=CallOptions(api_key="secret"))

    assert view.headers == {
        "X-Provider": "Token secret",
        "X-Endpoint": "endpoint",
    }
