from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from loushang.ai.auth import (
    ApiKeyAuth,
    OAuthBearerAuth,
    OAuthReauthenticationRequiredError,
)
from loushang.ai.auth.support import resolve_explicit_auth
from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.model import Model
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.ai.model.registry import get_default_model_registry


@dataclass(frozen=True)
class AuthResolution:
    provider: str
    model_id: str
    endpoint_id: str
    auth_required: bool
    satisfied: bool
    api_key: str | None = None
    api_key_env: str | None = None
    source: str | None = None
    message: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class AuthManager:
    def __init__(
        self,
        *,
        ai_registry: AiModelRegistry | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._ai_registry = (
            ai_registry if ai_registry is not None else get_default_model_registry()
        )
        self._env = dict(env) if env is not None else None

    @property
    def ai_registry(self) -> AiModelRegistry:
        return self._ai_registry

    @ai_registry.setter
    def ai_registry(self, value: AiModelRegistry) -> None:
        self._ai_registry = value

    def load_stored_oauth_credentials(self) -> dict[str, OAuthCredentials]:
        from loushang.ai.auth.storage import load_credentials

        return load_credentials()

    def get_api_key_for_model(self, model: Model) -> str | None:
        return self.resolve_for_model(model).api_key

    def resolve_for_model(self, model: Model) -> AuthResolution:
        endpoint = self._ai_registry.get_endpoint(model.provider_id, model.endpoint_id)
        provider = self._ai_registry.get_provider(model.provider_id)
        auth_config = (
            getattr(model, "auth", None)
            or (endpoint.auth if endpoint is not None else None)
            or (provider.auth if provider is not None else None)
        )
        auth_kind = getattr(auth_config, "kind", "apiKey")
        auth_required = auth_config is not None and auth_kind != "none"
        env = os.environ if self._env is None else self._env

        oauth_credentials: OAuthCredentials | None = None
        if auth_kind == "oauth":
            oauth_credentials = self._resolve_oauth_credentials(
                model.provider_id,
                endpoint_id=model.endpoint_id,
                model_id=model.id,
            )
            if oauth_credentials is not None:
                oauth_api_key = self._resolve_oauth_api_key(
                    model.provider_id,
                    oauth_credentials,
                    endpoint_id=model.endpoint_id,
                    model_id=model.id,
                )
                if oauth_api_key is not None:
                    return AuthResolution(
                        provider=model.provider_id,
                        model_id=model.id,
                        endpoint_id=model.endpoint_id,
                        auth_required=auth_required,
                        satisfied=True,
                        api_key=oauth_api_key,
                        api_key_env=getattr(auth_config, "api_key_env", None),
                        source="stored_oauth",
                        headers=resolve_explicit_auth(
                            OAuthBearerAuth(oauth_api_key),
                            declaration_hint=auth_config,
                            env=env,
                        ).headers,
                    )

        api_key_env = _primary_api_key_env(auth_config)
        api_key = _resolve_api_key_from_env(auth_config, env)
        if api_key:
            return AuthResolution(
                provider=model.provider_id,
                model_id=model.id,
                endpoint_id=model.endpoint_id,
                auth_required=auth_required,
                satisfied=True,
                api_key=api_key,
                api_key_env=api_key_env,
                source="env",
                headers=resolve_explicit_auth(
                    ApiKeyAuth(api_key),
                    declaration_hint=auth_config,
                    env=env,
                ).headers,
            )

        if not auth_required:
            return AuthResolution(
                provider=model.provider_id,
                model_id=model.id,
                endpoint_id=model.endpoint_id,
                auth_required=False,
                satisfied=True,
                source="none",
            )

        return AuthResolution(
            provider=model.provider_id,
            model_id=model.id,
            endpoint_id=model.endpoint_id,
            auth_required=True,
            satisfied=False,
            api_key_env=api_key_env,
            source="none",
            message=_build_missing_auth_message(
                provider=model.provider_id,
                model_id=model.id,
                api_key_env=api_key_env,
                has_stored_oauth=oauth_credentials is not None,
            ),
        )

    def _resolve_oauth_api_key(
        self,
        provider: str,
        credentials: OAuthCredentials,
        *,
        endpoint_id: str | None,
        model_id: str | None,
    ) -> str | None:
        try:
            from loushang.ai.auth.facade import resolve_oauth_api_key

            result = resolve_oauth_api_key(
                provider,
                credentials={provider: credentials},
                endpoint_id=endpoint_id,
                model_id=model_id,
                persist_refresh=False,
            )
        except OAuthReauthenticationRequiredError:
            raise
        except Exception:
            return None
        api_key = result.get("apiKey") if isinstance(result, Mapping) else None
        return api_key if isinstance(api_key, str) and api_key else None

    def _resolve_oauth_credentials(
        self,
        provider: str,
        *,
        endpoint_id: str | None,
        model_id: str | None,
    ) -> OAuthCredentials | None:
        try:
            from loushang.ai.auth.storage import (
                find_scoped_credential,
                load_credential_store,
            )

            return find_scoped_credential(
                load_credential_store(),
                provider,
                endpoint_id=endpoint_id,
                model_id=model_id,
            )
        except Exception:
            return None


def _build_missing_auth_message(
    *,
    provider: str,
    model_id: str,
    api_key_env: str | None,
    has_stored_oauth: bool,
) -> str:
    options: list[str] = []
    if api_key_env:
        options.append(f"set {api_key_env}")
    if not has_stored_oauth:
        options.append("store OAuth credentials")
    if not options:
        options.append("provide provider credentials")
    joined = " or ".join(options)
    return f"Missing auth for model '{provider}:{model_id}'; {joined}."


def _api_key_env_names(auth_config) -> tuple[str, ...]:
    if auth_config is None:
        return ()
    names: list[str] = []
    api_key_env = getattr(auth_config, "api_key_env", None)
    if isinstance(api_key_env, str) and api_key_env:
        names.append(api_key_env)
    for name in tuple(getattr(auth_config, "api_key_envs", ()) or ()):
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _primary_api_key_env(auth_config) -> str | None:
    names = _api_key_env_names(auth_config)
    return names[0] if names else None


def _resolve_api_key_from_env(auth_config, env: Mapping[str, str]) -> str | None:
    for name in _api_key_env_names(auth_config):
        value = env.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


__all__ = ["AuthManager", "AuthResolution"]
