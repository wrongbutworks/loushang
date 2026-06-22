from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from loushang.ai.auth.types import OAuthCredentials


def _auth_value(config, field_name: str, default=None):
    if config is None:
        return default
    return getattr(config, field_name, default)


@dataclass(frozen=True)
class AuthConfig:
    kind: str = "apiKey"
    api_key_env: str | None = None
    api_key_envs: tuple[str, ...] = ()
    header: str = "Authorization"
    prefix: str = "Bearer "
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthView:
    headers: dict[str, str] = field(default_factory=dict)
    account_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthInput:
    api_key: str | None = None
    oauth_credentials: dict[str, OAuthCredentials] | None = None
    headers: dict[str, str] = field(default_factory=dict)


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
            api_key_envs=tuple(_auth_value(override, "api_key_envs", ()) or ())
            or tuple(_auth_value(effective, "api_key_envs", ()) or ()),
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


def normalize_auth_input(options=None) -> AuthInput:
    if options is None:
        return AuthInput()
    oauth_credentials = getattr(options, "oauth_credentials", None)
    if not isinstance(oauth_credentials, dict):
        oauth_credentials = None
    headers = _str_dict(getattr(options, "headers", None))
    return AuthInput(
        api_key=_non_empty_str(getattr(options, "api_key", None)),
        oauth_credentials=oauth_credentials,
        headers=headers,
    )


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
    if api_key is None and bearer_token is None and config is not None:
        api_key = _resolve_api_key_from_env(config, resolved_env)

    if api_key is not None:
        if config is not None:
            headers[_auth_value(config, "header", "Authorization")] = (
                f"{_auth_value(config, 'prefix', 'Bearer ')}{api_key}"
            )
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    elif bearer_token is not None:
        headers["Authorization"] = f"Bearer {bearer_token}"
    extra = _expand_extra_headers(
        dict(_auth_value(config, "extra_headers", {}) or {}),
        resolved_env,
    )
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


def _resolve_env_oauth_auth_view(
    provider: str,
    env: dict[str, str] | None = None,
) -> AuthView | None:
    from loushang.ai.auth.env import get_env_oauth_credentials

    credentials = get_env_oauth_credentials(provider, env=env)
    if credentials is None:
        return None
    return _resolve_oauth_auth_view(provider, {provider: credentials})


def _resolve_stored_oauth_auth_view(
    provider: str,
    *,
    endpoint_id: str | None = None,
    model_id: str | None = None,
) -> AuthView | None:
    from loushang.ai.auth.storage import (
        find_scoped_credential,
        load_credential_store,
    )

    credential = find_scoped_credential(
        load_credential_store(),
        provider,
        endpoint_id=endpoint_id,
        model_id=model_id,
    )
    if credential is None:
        return None
    return _resolve_oauth_auth_view(provider, {provider: credential})


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
    auth_input = normalize_auth_input(options)
    endpoint = resolve_model_endpoint(model, registry=registry)
    auth_config = (
        getattr(model, "auth", None)
        or (endpoint.auth if endpoint is not None else None)
    )

    if isinstance(auth_input.oauth_credentials, dict):
        oauth_view = _resolve_oauth_auth_view(provider, auth_input.oauth_credentials)
        if oauth_view is not None:
            return oauth_view

    if auth_input.api_key is not None:
        return resolve_auth_material(api_key=auth_input.api_key, config=auth_config, env=env)

    oauth_view = _resolve_env_oauth_auth_view(provider, env=env)
    if oauth_view is not None:
        return oauth_view

    oauth_view = _resolve_stored_oauth_auth_view(
        provider,
        endpoint_id=getattr(model, "endpoint_id", None),
        model_id=getattr(model, "id", None),
    )
    if oauth_view is not None:
        return oauth_view

    if auth_config is None:
        return AuthView()
    return resolve_auth_material(config=auth_config, env=env)


def _resolve_api_key_from_env(config, env: Mapping[str, str]) -> str | None:
    for name in _api_key_env_names(config):
        value = env.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _api_key_env_names(config) -> tuple[str, ...]:
    names: list[str] = []
    for value in tuple(_auth_value(config, "api_key_envs", ()) or ()):
        if isinstance(value, str) and value:
            names.append(value)
    api_key_env = _auth_value(config, "api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        names.append(api_key_env)
    return tuple(dict.fromkeys(names))


def _expand_extra_headers(
    headers: dict[str, str],
    env: Mapping[str, str],
) -> dict[str, str]:
    expanded: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        env_name = _env_reference(value)
        if env_name is not None:
            env_value = env.get(env_name)
            if isinstance(env_value, str) and env_value:
                expanded[key] = env_value
            continue
        expanded[key] = value
    return expanded


def _env_reference(value: str) -> str | None:
    if not value.startswith("${") or not value.endswith("}"):
        return None
    name = value[2:-1].strip()
    return name or None


def _non_empty_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: entry
        for key, entry in value.items()
        if isinstance(key, str) and isinstance(entry, str)
    }
