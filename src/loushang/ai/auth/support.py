from __future__ import annotations

import os
from dataclasses import dataclass, field


def _auth_value(config, field_name: str, default=None):
    if config is None:
        return default
    return getattr(config, field_name, default)


@dataclass(frozen=True)
class AuthConfig:
    kind: str = "apiKey"
    api_key_env: str | None = None
    header: str = "Authorization"
    prefix: str = "Bearer "
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthView:
    headers: dict[str, str] = field(default_factory=dict)
    account_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def merge_auth_config(
    provider_auth=None,
    endpoint_auth=None,
    binding_auth=None,
):
    effective = provider_auth
    for override in (endpoint_auth, binding_auth):
        if override is None:
            continue
        if effective is None:
            effective = override
            continue
        auth_type = type(effective)
        effective = auth_type(
            kind=_auth_value(override, "kind", "apiKey")
            or _auth_value(effective, "kind", "apiKey"),
            api_key_env=_auth_value(override, "api_key_env")
            or _auth_value(effective, "api_key_env"),
            header=_auth_value(override, "header", "Authorization")
            or _auth_value(effective, "header", "Authorization"),
            prefix=_auth_value(override, "prefix")
            if _auth_value(override, "prefix") is not None
            else _auth_value(effective, "prefix", "Bearer "),
            extra_headers={
                **dict(_auth_value(effective, "extra_headers", {}) or {}),
                **dict(_auth_value(override, "extra_headers", {}) or {}),
            },
        )
    return effective


def resolve_auth_material(
    *,
    api_key: str | None = None,
    bearer_token: str | None = None,
    extra_headers: dict[str, str] | None = None,
    config=None,
    env: dict[str, str] | None = None,
) -> AuthView:
    headers: dict[str, str] = {}
    resolved_env = os.environ if env is None else env
    if (
        api_key is None
        and bearer_token is None
        and config is not None
        and _auth_value(config, "api_key_env")
    ):
        api_key = resolved_env.get(_auth_value(config, "api_key_env"))

    if api_key is not None:
        if config is not None:
            headers[_auth_value(config, "header", "Authorization")] = (
                f"{_auth_value(config, 'prefix', 'Bearer ')}{api_key}"
            )
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    elif bearer_token is not None:
        headers["Authorization"] = f"Bearer {bearer_token}"
    extra = dict(_auth_value(config, "extra_headers", {}) or {})
    if extra:
        headers.update(extra)
    if extra_headers:
        headers.update(extra_headers)
    return AuthView(headers=headers)


def _resolve_oauth_auth_view(
    provider: str, oauth_credentials: dict | None
) -> AuthView | None:
    if not oauth_credentials:
        return None
    try:
        from loushang.ai.auth.oauth import get_oauth_api_key

        result = get_oauth_api_key(provider, oauth_credentials)  # type: ignore[arg-type]
        if result is None:
            return None
        credentials = result["newCredentials"]
        metadata = dict(getattr(credentials, "extra", None) or {})
        account_id = metadata.get("account_id")
        if not isinstance(account_id, str) or not account_id:
            account_id = metadata.get("chatgpt_account_id")
        if not isinstance(account_id, str) or not account_id:
            account_id = None
        return AuthView(
            headers=resolve_auth_material(bearer_token=result["apiKey"]).headers,
            account_id=account_id,
            metadata=metadata,
        )
    except Exception:
        return None


def _resolve_env_oauth_auth_view(
    provider: str,
    env: dict[str, str] | None = None,
) -> AuthView | None:
    try:
        from loushang.ai.auth.env import get_env_oauth_credentials

        credentials = get_env_oauth_credentials(provider, env=env)
    except Exception:
        return None
    if credentials is None:
        return None
    return _resolve_oauth_auth_view(provider, {provider: credentials})


def _resolve_stored_oauth_auth_view(provider: str) -> AuthView | None:
    try:
        from loushang.ai.auth.storage import load_credentials

        stored = load_credentials()
    except Exception:
        return None
    if not stored:
        return None
    return _resolve_oauth_auth_view(provider, stored)


def resolve_auth_for_model(
    model,
    *,
    catalog=None,
    options=None,
    env: dict[str, str] | None = None,
    registry=None,
) -> AuthView:
    del catalog
    from loushang.ai.model.registry import resolve_model_endpoint

    provider = model.provider_id
    oauth_credentials = (
        getattr(options, "oauth_credentials", None) if options is not None else None
    )

    if isinstance(oauth_credentials, dict):
        oauth_view = _resolve_oauth_auth_view(provider, oauth_credentials)
        if oauth_view is not None:
            return oauth_view

    if getattr(options, "api_key", None) is not None:
        return resolve_auth_material(api_key=options.api_key)

    oauth_view = _resolve_env_oauth_auth_view(provider, env=env)
    if oauth_view is not None:
        return oauth_view

    oauth_view = _resolve_stored_oauth_auth_view(provider)
    if oauth_view is not None:
        return oauth_view

    endpoint = resolve_model_endpoint(model, registry=registry)
    auth_config = (
        endpoint.auth if endpoint is not None else getattr(model, "auth", None)
    )
    if auth_config is None:
        return AuthView()
    return resolve_auth_material(config=auth_config, env=env)
