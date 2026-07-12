from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from loushang.ai.auth.credentials import (
    ApiKeyAuth,
    AuthCredential,
    HeadersAuth,
    NoAuth,
    OAuthBearerAuth,
)
from loushang.ai.errors import AIAuthenticationError, AIConfigurationError
from loushang.ai.model import Auth
from loushang.observability.problem import JSONValue

AuthConfig = Auth

_HTTP_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


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
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


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
    resolved_env = os.environ if env is None else env
    if explicit_auth is not None:
        return resolve_explicit_auth(
            explicit_auth,
            declaration_hint=declaration,
            provider_id=getattr(model, "provider_id", None),
            env=resolved_env,
        )
    return resolve_default_auth(declaration, model=model, env=resolved_env)


def resolve_explicit_auth(
    auth: AuthCredential,
    *,
    declaration_hint=None,
    provider_id: str | None = None,
    env: Mapping[str, str] | None = None,
) -> AuthView:
    return _resolve_typed_explicit_auth(
        auth,
        declaration_hint=declaration_hint,
        provider_id=provider_id,
        env=os.environ if env is None else env,
    )


def _resolve_typed_explicit_auth(
    auth: AuthCredential,
    *,
    declaration_hint=None,
    provider_id: str | None = None,
    env: Mapping[str, str],
) -> AuthView:
    if isinstance(auth, NoAuth):
        return AuthView(headers={})

    if isinstance(auth, HeadersAuth):
        resolved_headers = _validated_headers(
            auth.headers,
            source="HeadersAuth.headers",
        )
        if not resolved_headers:
            raise AuthResolutionError(
                "HeadersAuth.headers must be non-empty; use NoAuth() for no auth.",
                details={"field": "HeadersAuth.headers"},
            )
        return AuthView(headers=resolved_headers)

    if isinstance(auth, ApiKeyAuth):
        header, prefix = _resolve_header_prefix(
            header=auth.header,
            prefix=auth.prefix,
            declaration_hint=declaration_hint,
        )
        return AuthView(
            headers=_build_auth_headers(
                header=header,
                value=f"{prefix}{_validated_secret(auth.value, field_name='auth.value')}",
                declaration=declaration_hint,
                env=env,
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
                value=(
                    f"{prefix}"
                    f"{_validated_secret(auth.access_token, field_name='auth.access_token')}"
                ),
                declaration=declaration_hint,
                env=env,
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
                value=(
                    f"{prefix}"
                    f"{_validated_secret(api_key, field_name='models.json.auth api key env')}"
                ),
                declaration=declaration,
                env=os.environ if env is None else env,
            )
        )

    if kind == "oauth":
        raise MissingAuthError(
            "Model declares oauth auth; provide CallOptions.auth=OAuthBearerAuth(...).",
            provider=getattr(model, "provider_id", None),
            endpoint=getattr(model, "endpoint_id", None),
            model=getattr(model, "id", None),
            details={"expected_auth": "oauth"},
        )

    if kind == "none":
        return AuthView(headers={})

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
    header_from_declaration = False
    if header is not None and not isinstance(header, str):
        raise AuthResolutionError(
            "auth header must be a string.",
            details={"field": "header"},
        )
    resolved_header = header
    if resolved_header is None:
        declared_header = _auth_value(declaration_hint, "header", None)
        if declared_header is not None and not isinstance(declared_header, str):
            raise InvalidAuthConfigError(
                "models.json.auth.header must be a string.",
                details={"field": "header"},
            )
        resolved_header = declared_header
        header_from_declaration = resolved_header is not None
    if resolved_header is None:
        resolved_header = "Authorization"

    prefix_from_declaration = False
    if prefix is not None and not isinstance(prefix, str):
        raise AuthResolutionError(
            "auth prefix must be a string.",
            details={"field": "prefix"},
        )
    resolved_prefix = prefix
    if resolved_prefix is None:
        declared_prefix = _auth_value(declaration_hint, "prefix", None)
        if declared_prefix is not None and not isinstance(declared_prefix, str):
            raise InvalidAuthConfigError(
                "models.json.auth.prefix must be a string.",
                details={"field": "prefix"},
            )
        resolved_prefix = declared_prefix
        prefix_from_declaration = resolved_prefix is not None
    if resolved_prefix is None:
        resolved_prefix = "Bearer "

    _validate_header_name(
        resolved_header,
        source="auth header",
        invalid_config=header_from_declaration,
    )
    if "\r" in resolved_prefix or "\n" in resolved_prefix:
        raise _auth_validation_error(
            "auth prefix must not contain CR or LF.",
            details={"field": "prefix"},
            invalid_config=prefix_from_declaration,
        )
    return resolved_header, resolved_prefix


def _resolve_api_key_from_env(config, env: Mapping[str, str]) -> str | None:
    for name in _api_key_env_names(config):
        value = env.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _api_key_env_names(config) -> tuple[str, ...]:
    names: list[str] = []
    api_key_env = _auth_value(config, "api_key_env")
    if isinstance(api_key_env, str) and api_key_env:
        names.append(api_key_env)
    for value in tuple(_auth_value(config, "api_key_envs", ()) or ()):
        if isinstance(value, str) and value:
            names.append(value)
    return tuple(dict.fromkeys(names))


def _build_auth_headers(
    *,
    header: str,
    value: str,
    declaration,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    headers = {header: value}
    headers.update(_extra_headers_without_primary_conflict(declaration, header, env))
    return _validated_headers(headers, source="resolved auth headers")


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
    expanded = _expand_extra_headers(
        dict(_auth_value(declaration, "extra_headers", {}) or {}),
        resolved_env,
    )
    return _validated_headers(
        expanded,
        source="models.json.auth.extraHeaders",
        invalid_config=True,
    )


def _expand_extra_headers(
    headers: Mapping[str, str],
    env: Mapping[str, str],
) -> dict[str, str]:
    expanded: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise InvalidAuthConfigError(
                "models.json.auth.extraHeaders must contain string names and values."
            )
        env_name = _env_reference(value)
        if env_name is not None:
            env_value = env.get(env_name)
            if not isinstance(env_value, str) or not env_value:
                raise InvalidAuthConfigError(
                    "models.json.auth.extraHeaders references a missing environment variable.",
                    details={"expected_env": env_name, "header": key},
                )
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
    if "\r" in resolved or "\n" in resolved:
        raise AuthResolutionError(
            f"{field_name} must not contain CR or LF.",
            details={"field": field_name},
        )
    return resolved


def _validated_headers(
    value: object,
    *,
    source: str,
    invalid_config: bool = False,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise _auth_validation_error(
            f"{source} must be a mapping of strings.",
            details={"field": source},
            invalid_config=invalid_config,
        )
    resolved: dict[str, str] = {}
    normalized_names: dict[str, str] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not key:
            raise _auth_validation_error(
                f"{source} keys must be non-empty strings.",
                details={"field": source},
                invalid_config=invalid_config,
            )
        _validate_header_name(
            key,
            source=source,
            invalid_config=invalid_config,
        )
        if not isinstance(entry, str) or not entry:
            raise _auth_validation_error(
                f"{source} values must be non-empty strings.",
                details={"field": source},
                invalid_config=invalid_config,
            )
        if "\r" in entry or "\n" in entry:
            raise _auth_validation_error(
                f"{source} values must not contain CR or LF.",
                details={"field": source, "header": key},
                invalid_config=invalid_config,
            )
        normalized_name = key.casefold()
        previous_key = normalized_names.get(normalized_name)
        if previous_key is not None:
            raise _auth_validation_error(
                f"{source} contains duplicate case-insensitive header names.",
                details={
                    "field": source,
                    "header": key,
                    "conflicts_with": previous_key,
                },
                invalid_config=invalid_config,
            )
        normalized_names[normalized_name] = key
        resolved[key] = entry
    return resolved


def _validate_header_name(
    value: str,
    *,
    source: str,
    invalid_config: bool = False,
) -> None:
    if not _HTTP_TOKEN.fullmatch(value):
        raise _auth_validation_error(
            f"{source} contains an invalid HTTP header name.",
            details={"field": source, "header": value},
            invalid_config=invalid_config,
        )


def _auth_validation_error(
    message: str,
    *,
    details: Mapping[str, JSONValue],
    invalid_config: bool,
) -> AIAuthenticationError | AIConfigurationError:
    error_type = InvalidAuthConfigError if invalid_config else AuthResolutionError
    return error_type(message, details=details)


def _env_reference(value: str) -> str | None:
    if not value.startswith("${") or not value.endswith("}"):
        return None
    name = value[2:-1].strip()
    return name or None
