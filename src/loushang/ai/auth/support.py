from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from loushang.ai.auth.credentials import (
    ApiKeyAuth,
    AuthCredential,
    HeadersAuth,
    NoAuth,
    OAuthBearerAuth,
)
from loushang.ai.errors import AIAuthenticationError, AIConfigurationError
from loushang.ai.model import Auth
from loushang.auth.types import OAuthCredentials

AuthConfig = Auth


def _auth_value(config, field_name: str, default=None):
    if config is None:
        return default
    return getattr(config, field_name, default)


_AUTH_FIELD_DEFAULTS: dict[str, object] = {
    "kind": "apiKey",
    "api_key_env": None,
    "api_key_envs": (),
    "header": "Authorization",
    "prefix": "Bearer ",
    "extra_headers": {},
}
_AUTH_ATTR_TO_RAW_KEY = {
    "kind": "kind",
    "api_key_env": "apiKeyEnv",
    "api_key_envs": "apiKeyEnvs",
    "header": "header",
    "prefix": "prefix",
    "extra_headers": "extraHeaders",
}


class MissingAuthError(AIAuthenticationError):
    pass


class MissingAuthConfigError(AIConfigurationError):
    pass


class InvalidAuthConfigError(AIConfigurationError):
    pass


class AuthResolutionError(AIAuthenticationError):
    pass


@dataclass(frozen=True)
class AuthView:
    headers: dict[str, str] = field(default_factory=dict, repr=False)


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
        extra_headers = dict(_auth_value(effective, "extra_headers", {}) or {})
        if _auth_field_explicit(override, "extra_headers"):
            extra_headers.update(dict(_auth_value(override, "extra_headers", {}) or {}))
        effective = auth_type(
            kind=_merged_auth_value(effective, override, "kind"),
            api_key_env=_merged_auth_value(effective, override, "api_key_env"),
            api_key_envs=tuple(
                _merged_auth_value(effective, override, "api_key_envs") or ()
            ),
            header=_merged_auth_value(effective, override, "header"),
            prefix=_merged_auth_value(effective, override, "prefix"),
            extra_headers=extra_headers,
        )
    return effective


def resolve_auth_for_model(
    model,
    *,
    options=None,
    env: Mapping[str, str] | None = None,
) -> AuthView:
    return resolve_auth_for_request(model, options=options, env=env)


def resolve_auth_for_request(
    model,
    *,
    options=None,
    env: Mapping[str, str] | None = None,
) -> AuthView:
    declaration = getattr(model, "auth", None)
    explicit_auth = getattr(options, "auth", None) if options is not None else None
    api_key = getattr(options, "api_key", None) if options is not None else None
    oauth_credentials = (
        getattr(options, "oauth_credentials", None) if options is not None else None
    )
    headers = getattr(options, "headers", None) if options is not None else None
    if explicit_auth is not None:
        return resolve_explicit_auth(
            explicit_auth,
            declaration_hint=declaration,
        )
    if api_key is not None or oauth_credentials is not None:
        return resolve_explicit_auth(
            api_key=api_key,
            oauth_credentials=oauth_credentials,
            declaration_hint=declaration,
            provider_id=getattr(model, "provider_id", None),
            headers=headers,
        )
    return resolve_default_auth(declaration, model=model, env=env, headers=headers)


def resolve_explicit_auth(
    auth: AuthCredential | None = None,
    *,
    api_key: str | None = None,
    oauth_credentials: OAuthCredentials | None = None,
    declaration_hint=None,
    provider_id: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> AuthView:
    if auth is not None:
        if api_key is not None or oauth_credentials is not None or headers:
            raise AuthResolutionError(
                "auth cannot be combined with api_key, oauth_credentials, or headers."
            )
        return _resolve_legacy_explicit_auth(
            auth,
            declaration_hint=declaration_hint,
        )

    if api_key is not None and oauth_credentials is not None:
        raise AuthResolutionError(
            "api_key and oauth_credentials are mutually exclusive."
        )

    if api_key is not None:
        _validate_explicit_credential_kind(
            declaration_hint,
            provided_kind="api_key",
            provided_field="api_key",
            provider_id=provider_id,
        )
        resolved_api_key = _validated_secret(api_key, field_name="api_key")
        header, prefix = _resolve_header_prefix(
            declaration_hint=declaration_hint,
        )
        return AuthView(
            headers=_build_auth_headers(
                header=header,
                value=f"{prefix}{resolved_api_key}",
                declaration=declaration_hint,
                additional_headers=(("CallOptions.headers", headers),),
            )
        )

    if oauth_credentials is not None:
        if not isinstance(oauth_credentials, OAuthCredentials):
            raise AuthResolutionError(
                "oauth_credentials must be OAuthCredentials.",
                details={"credential_type": type(oauth_credentials).__name__},
            )
        credential_provider = _validated_secret(
            oauth_credentials.provider,
            field_name="oauth_credentials.provider",
        )
        if provider_id is not None and credential_provider != provider_id:
            raise AuthResolutionError(
                "OAuth credential provider does not match model provider.",
                provider=provider_id,
                details={
                    "provided_provider": credential_provider,
                    "model_provider": provider_id,
                },
            )
        _validate_explicit_credential_kind(
            declaration_hint,
            provided_kind="oauth",
            provided_field="oauth_credentials",
            provider_id=provider_id,
        )
        access_token = _validated_secret(
            oauth_credentials.access_token,
            field_name="oauth_credentials.access_token",
        )
        header, prefix = _resolve_header_prefix(
            declaration_hint=declaration_hint,
        )
        return AuthView(
            headers=_build_auth_headers(
                header=header,
                value=f"{prefix}{access_token}",
                declaration=declaration_hint,
                additional_headers=(("CallOptions.headers", headers),),
            )
        )

    raise AuthResolutionError("No explicit credential was provided.")


def _resolve_legacy_explicit_auth(
    auth: AuthCredential,
    *,
    declaration_hint=None,
) -> AuthView:
    if isinstance(auth, NoAuth):
        return AuthView()

    if isinstance(auth, HeadersAuth):
        return AuthView(headers=_str_mapping(auth.headers))

    if isinstance(auth, ApiKeyAuth):
        header, prefix = _resolve_header_prefix(
            header=auth.header,
            prefix=auth.prefix,
            declaration_hint=declaration_hint,
        )
        return AuthView(
            headers=_build_auth_headers(
                header=header,
                value=f"{prefix}{auth.value}",
                declaration=declaration_hint,
            )
        )

    if isinstance(auth, OAuthBearerAuth):
        header, prefix = _resolve_header_prefix(
            header=auth.header,
            prefix=auth.prefix,
            declaration_hint=declaration_hint,
        )
        return AuthView(
            headers=_build_auth_headers(
                header=header,
                value=f"{prefix}{auth.access_token}",
                declaration=declaration_hint,
            )
        )

    raise AuthResolutionError(
        "Unsupported CallOptions.auth credential type.",
        details={"auth_type": type(auth).__name__},
    )


def resolve_default_auth(
    declaration,
    *,
    model,
    env: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
) -> AuthView:
    if declaration is None:
        raise MissingAuthConfigError(
            "No explicit auth and no default auth declaration.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
        )

    kind = normalize_auth_kind(_auth_value(declaration, "kind", None))
    if kind == "api_key":
        env_names = _api_key_env_names(declaration)
        api_key = _resolve_api_key_from_env(
            declaration, os.environ if env is None else env
        )
        if api_key is None:
            raise MissingAuthError(
                "Model requires api_key auth but no configured API key env is set.",
                provider=getattr(model, "provider_id", None),
                endpoint=getattr(model, "endpoint_id", None),
                model=getattr(model, "id", None),
                details={"expected_env": list(env_names)},
            )
        header, prefix = _resolve_header_prefix(declaration_hint=declaration)
        return AuthView(
            headers=_build_auth_headers(
                header=header,
                value=f"{prefix}{api_key}",
                declaration=declaration,
                env=os.environ if env is None else env,
                additional_headers=(("CallOptions.headers", headers),),
            )
        )

    if kind == "oauth":
        raise MissingAuthError(
            "Model declares oauth auth; provide CallOptions.oauth_credentials.",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={"expected_auth": "oauth"},
        )

    if kind == "none":
        primary_header, _ = _resolve_header_prefix(declaration_hint=declaration)
        return AuthView(
            headers=_merge_non_primary_headers(
                _extra_headers_without_primary_conflict(
                    declaration,
                    primary_header,
                    os.environ if env is None else env,
                ),
                primary_header=primary_header,
                additional_headers=(("CallOptions.headers", headers),),
            )
        )

    raise InvalidAuthConfigError(
        "Unsupported model auth kind.",
        provider=getattr(model, "provider_id", None),
        endpoint=getattr(model, "endpoint_id", None),
        model=getattr(model, "id", None),
        details={"auth_kind": str(kind)},
    )


def normalize_auth_kind(kind: str | None) -> str | None:
    if kind is None:
        return None
    normalized = kind.strip().replace("-", "_")
    lowered = normalized.lower()
    if lowered in {"apikey", "api_key"}:
        return "api_key"
    if lowered == "oauth":
        return "oauth"
    if lowered == "none":
        return "none"
    return normalized


def _validate_explicit_credential_kind(
    declaration_hint,
    *,
    provided_kind: str,
    provided_field: str,
    provider_id: str | None,
) -> None:
    if declaration_hint is None:
        return
    declaration_kind = normalize_auth_kind(_auth_value(declaration_hint, "kind", None))
    if declaration_kind == provided_kind:
        return
    raise AuthResolutionError(
        f"{provided_field} cannot satisfy a model that declares "
        f"{declaration_kind or 'unspecified'} auth.",
        provider=provider_id,
        details={
            "auth_kind": declaration_kind or "unspecified",
            "provided_kind": provided_kind,
        },
    )


def _auth_field_explicit(config, field_name: str) -> bool:
    explicit_keys = getattr(config, "_explicit_keys", None)
    raw_key = _AUTH_ATTR_TO_RAW_KEY[field_name]
    if explicit_keys is not None:
        return raw_key in explicit_keys
    value = _auth_value(config, field_name, _AUTH_FIELD_DEFAULTS[field_name])
    if field_name == "api_key_env":
        return value is not None
    if field_name == "api_key_envs":
        return bool(tuple(value or ()))
    if field_name == "extra_headers":
        return bool(dict(value or {}))
    return value != _AUTH_FIELD_DEFAULTS[field_name]


def _merged_auth_value(effective, override, field_name: str):
    if _auth_field_explicit(override, field_name):
        return _auth_value(override, field_name, _AUTH_FIELD_DEFAULTS[field_name])
    return _auth_value(effective, field_name, _AUTH_FIELD_DEFAULTS[field_name])


def _resolve_header_prefix(
    *,
    header: str | None = None,
    prefix: str | None = None,
    declaration_hint=None,
) -> tuple[str, str]:
    resolved_header = header
    if resolved_header is None:
        declared_header = _auth_value(declaration_hint, "header", None)
        resolved_header = declared_header if isinstance(declared_header, str) else None
    if not resolved_header:
        resolved_header = "Authorization"

    resolved_prefix = prefix
    if resolved_prefix is None:
        declared_prefix = _auth_value(declaration_hint, "prefix", None)
        resolved_prefix = declared_prefix if isinstance(declared_prefix, str) else None
    if resolved_prefix is None:
        resolved_prefix = "Bearer "

    return resolved_header, resolved_prefix


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


def _build_auth_headers(
    *,
    header: str,
    value: str,
    declaration,
    env: Mapping[str, str] | None = None,
    additional_headers: tuple[
        tuple[str, Mapping[str, str] | None],
        ...,
    ] = (),
) -> dict[str, str]:
    headers = {header: value}
    headers.update(_extra_headers_without_primary_conflict(declaration, header, env))
    return _merge_non_primary_headers(
        headers,
        primary_header=header,
        additional_headers=additional_headers,
    )


def _merge_non_primary_headers(
    headers: dict[str, str],
    *,
    primary_header: str,
    additional_headers: tuple[
        tuple[str, Mapping[str, str] | None],
        ...,
    ],
) -> dict[str, str]:
    merged = dict(headers)
    for source, values in additional_headers:
        if values is None:
            continue
        normalized = _validated_headers(values, source=source)
        conflicting_header = _find_header_case_insensitive(
            normalized,
            primary_header,
        )
        if conflicting_header is not None:
            raise InvalidAuthConfigError(
                f"{source} cannot override the primary auth header.",
                details={
                    "conflicting_header": conflicting_header,
                    "primary_header": primary_header,
                    "source": source,
                },
            )
        merged.update(normalized)
    return merged


def _extra_headers_without_primary_conflict(
    declaration,
    primary_header: str,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    _validate_extra_headers_do_not_override_primary(declaration, primary_header)
    return _extra_headers(declaration, env)


def _validate_extra_headers_do_not_override_primary(
    declaration,
    primary_header: str,
) -> None:
    if declaration is None:
        return
    extra_headers = dict(_auth_value(declaration, "extra_headers", {}) or {})
    conflicting_header = _find_header_case_insensitive(
        extra_headers.keys(),
        primary_header,
    )
    if conflicting_header is None:
        return
    raise InvalidAuthConfigError(
        "models.json.auth.extraHeaders cannot override the primary auth header.",
        details={
            "conflicting_header": conflicting_header,
            "primary_header": primary_header,
        },
    )


def _find_header_case_insensitive(
    headers: Iterable[object],
    target: str,
) -> str | None:
    target_lower = target.lower()
    for header in headers:
        if isinstance(header, str) and header.lower() == target_lower:
            return header
    return None


def _extra_headers(
    declaration,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    if declaration is None:
        return {}
    resolved_env = os.environ if env is None else env
    return _expand_extra_headers(
        dict(_auth_value(declaration, "extra_headers", {}) or {}),
        resolved_env,
    )


def _expand_extra_headers(
    headers: Mapping[str, str],
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


def _validated_secret(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise AuthResolutionError(
            f"{field_name} must be a string.",
            details={"field": field_name},
        )
    resolved = value.strip()
    if not resolved:
        raise AuthResolutionError(
            f"{field_name} must be non-empty.",
            details={"field": field_name},
        )
    return resolved


def _validated_headers(value: object, *, source: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AuthResolutionError(
            f"{source} must be a mapping of strings.",
            details={"field": source},
        )
    resolved: dict[str, str] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not key:
            raise AuthResolutionError(
                f"{source} keys must be non-empty strings.",
                details={"field": source},
            )
        if not isinstance(entry, str) or not entry:
            raise AuthResolutionError(
                f"{source} values must be non-empty strings.",
                details={"field": source},
            )
        resolved[key] = entry
    return resolved


def _str_mapping(value: Mapping[str, str]) -> dict[str, str]:
    return {
        key: entry
        for key, entry in value.items()
        if isinstance(key, str) and isinstance(entry, str)
    }


def _env_reference(value: str) -> str | None:
    if not value.startswith("${") or not value.endswith("}"):
        return None
    name = value[2:-1].strip()
    return name or None
