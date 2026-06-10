from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

from loushang.ai.auth.types import OAuthAuthInfo, OAuthLoginCallbacks, OAuthPrompt
from loushang.ai.model import Model
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry

AuthScope = Literal["provider", "endpoint", "model"]


@dataclass(frozen=True)
class AuthLoginTarget:
    provider: str
    endpoint_id: str | None = None
    model_id: str | None = None
    scope: AuthScope = "provider"
    auth_kind: str | None = None


@dataclass
class SessionOAuthLoginCallbacks(OAuthLoginCallbacks):
    auth_info: OAuthAuthInfo | None = None
    progress: list[str] = field(default_factory=list)

    def on_auth(self, info: OAuthAuthInfo) -> None:
        self.auth_info = cast(OAuthAuthInfo, dict(info))

    async def on_prompt(self, prompt: OAuthPrompt) -> str:
        message = prompt.get("message") or "OAuth login requires manual code input."
        raise RuntimeError(self._manual_input_unavailable_message(str(message)))

    def on_progress(self, message: str) -> None:
        self.progress.append(message)

    async def on_manual_code_input(self) -> str:
        return ""

    @property
    def signal(self) -> object | None:
        return None

    def _manual_input_unavailable_message(self, message: str) -> str:
        auth_url = (self.auth_info or {}).get("url")
        if isinstance(auth_url, str) and auth_url:
            return f"{message} TUI manual code entry is not available yet. Open this URL and retry if needed: {auth_url}"
        return f"{message} TUI manual code entry is not available yet."


def resolve_auth_login_target(
    raw_target: str | None,
    *,
    current_model: Model | None,
    registry: AiModelRegistry,
) -> AuthLoginTarget:
    if raw_target is None:
        if current_model is None:
            raise ValueError("No active model is available for /login.")
        return _target_from_current_model(current_model, registry=registry)

    parts = raw_target.split(":")
    if len(parts) == 1:
        provider = _require_part(parts[0], "provider")
        auth_kind = _provider_auth_kind(registry, provider)
        return AuthLoginTarget(provider=provider, scope="provider", auth_kind=auth_kind)
    if len(parts) == 2:
        provider = _require_part(parts[0], "provider")
        endpoint_id = _require_part(parts[1], "endpoint")
        endpoint = registry.get_endpoint(provider, endpoint_id)
        if endpoint is None:
            raise ValueError(f"Endpoint not found: {provider}:{endpoint_id}")
        return AuthLoginTarget(
            provider=provider,
            endpoint_id=endpoint_id,
            scope="endpoint",
            auth_kind=_auth_kind(getattr(endpoint, "auth", None))
            or _provider_auth_kind(registry, provider),
        )
    if len(parts) == 3:
        provider = _require_part(parts[0], "provider")
        endpoint_id = _require_part(parts[1], "endpoint")
        model_id = _require_part(parts[2], "model")
        model = registry.find_model(provider, endpoint_id, model_id)
        if model is None:
            raise ValueError(f"Model not found: {provider}:{endpoint_id}:{model_id}")
        return AuthLoginTarget(
            provider=provider,
            endpoint_id=endpoint_id,
            model_id=model_id,
            scope="model",
            auth_kind=_auth_kind(getattr(model, "auth", None))
            or _endpoint_auth_kind(registry, provider, endpoint_id)
            or _provider_auth_kind(registry, provider),
        )
    raise ValueError("Usage: /login [provider[:endpoint[:model]]]")


def validate_oauth_login_target(target: AuthLoginTarget) -> None:
    if target.auth_kind != "oauth":
        ref = target.provider
        if target.endpoint_id:
            ref = f"{ref}:{target.endpoint_id}"
        if target.model_id:
            ref = f"{ref}:{target.model_id}"
        raise ValueError(f"OAuth login is not configured for {ref}.")


def login_scope_kwargs(target: AuthLoginTarget) -> dict[str, str | None]:
    if target.scope == "model":
        return {"endpoint_id": target.endpoint_id, "model_id": target.model_id}
    if target.scope == "endpoint":
        return {"endpoint_id": target.endpoint_id, "model_id": None}
    return {"endpoint_id": None, "model_id": None}


def _target_from_current_model(model: Model, *, registry: AiModelRegistry) -> AuthLoginTarget:
    provider = model.provider_id
    endpoint_id = model.endpoint_id
    model_id = model.id
    model_auth = getattr(model, "auth", None)
    if model_auth is not None and not bool(getattr(model, "_auth_inherited", False)):
        return AuthLoginTarget(
            provider=provider,
            endpoint_id=endpoint_id,
            model_id=model_id,
            scope="model",
            auth_kind=_auth_kind(model_auth),
        )

    endpoint = registry.get_endpoint(provider, endpoint_id)
    provider_auth_kind = _provider_auth_kind(registry, provider)
    endpoint_auth = getattr(endpoint, "auth", None) if endpoint is not None else None
    if endpoint_auth is not None and not bool(getattr(endpoint, "_auth_inherited", False)):
        return AuthLoginTarget(
            provider=provider,
            endpoint_id=endpoint_id,
            scope="endpoint",
            auth_kind=_auth_kind(endpoint_auth),
        )
    if provider_auth_kind is not None:
        return AuthLoginTarget(provider=provider, scope="provider", auth_kind=provider_auth_kind)
    if endpoint_auth is not None:
        return AuthLoginTarget(
            provider=provider,
            endpoint_id=endpoint_id,
            scope="endpoint",
            auth_kind=_auth_kind(endpoint_auth),
        )
    return AuthLoginTarget(provider=provider, scope="provider", auth_kind=None)


def _provider_auth_kind(registry: AiModelRegistry, provider: str) -> str | None:
    resolved = registry.get_provider(provider)
    if resolved is None:
        raise ValueError(f"Provider not found: {provider}")
    return _auth_kind(getattr(resolved, "auth", None))


def _endpoint_auth_kind(
    registry: AiModelRegistry,
    provider: str,
    endpoint_id: str,
) -> str | None:
    endpoint = registry.get_endpoint(provider, endpoint_id)
    if endpoint is None:
        raise ValueError(f"Endpoint not found: {provider}:{endpoint_id}")
    return _auth_kind(getattr(endpoint, "auth", None))


def _auth_kind(auth: Any) -> str | None:
    kind = getattr(auth, "kind", None)
    return kind if isinstance(kind, str) and kind else None


def _require_part(value: str, label: str) -> str:
    if not value:
        raise ValueError(f"Login target requires {label}.")
    return value


__all__ = [
    "AuthLoginTarget",
    "SessionOAuthLoginCallbacks",
    "login_scope_kwargs",
    "resolve_auth_login_target",
    "validate_oauth_login_target",
]
