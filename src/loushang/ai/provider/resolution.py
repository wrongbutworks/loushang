from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import Any

from loushang.ai.auth.support import resolve_auth_for_model
from loushang.ai.context import NormalizedContext
from loushang.ai.model import Model
from loushang.ai.model.domain import (
    AdapterConfig,
    AnthropicMessagesConfig,
    Endpoint,
    OpenAICompletionsConfig,
    OpenAIResponsesConfig,
    default_adapter_config,
)
from loushang.ai.options import get_max_output_tokens, get_reasoning_effort
from loushang.ai.provider.protocol import ProviderContext, ProviderRequest


def ensure_request_api(provider_api: str, request: ProviderRequest) -> ProviderRequest:
    if request.api != provider_api:
        raise ValueError(
            f"Mismatched api: provider={provider_api!r} request.api={request.api!r}"
        )
    return request


def normalize_provider_request_for_api(
    provider_api: str,
    request: ProviderRequest,
) -> ProviderRequest:
    request = ensure_request_api(provider_api, request)
    if provider_api == "openai-completions":
        adapter_config = _ensure_core_adapter_config(
            request.adapter_config,
            provider_api,
            OpenAICompletionsConfig,
        )
        return replace(request, adapter_config=adapter_config)
    if provider_api == "openai-responses":
        adapter_config = _ensure_core_adapter_config(
            request.adapter_config,
            provider_api,
            OpenAIResponsesConfig,
        )
        return replace(request, adapter_config=adapter_config)
    if provider_api == "anthropic-messages":
        adapter_config = _ensure_core_adapter_config(
            request.adapter_config,
            provider_api,
            AnthropicMessagesConfig,
        )
        return replace(request, adapter_config=adapter_config)
    return request


def _ensure_core_adapter_config(
    adapter_config: object | None,
    api: str,
    expected_type: type[AdapterConfig],
) -> AdapterConfig:
    if adapter_config is None:
        resolved = default_adapter_config(api)
        if resolved is None:
            raise ValueError(f"No default adapter config for api: {api}")
        return resolved
    if not isinstance(adapter_config, expected_type):
        raise TypeError(f"adapter_config for {api} must be {expected_type.__name__}")
    return adapter_config


def resolve_endpoint_for_model(
    model: Model,
) -> Endpoint | None:
    identity = _concrete_model_identity(model)
    if identity is None:
        return None
    provider_id, endpoint_id, api = identity
    return Endpoint(
        id=endpoint_id,
        provider=provider_id,
        api=api,
        base_url=model.base_url,
        base_url_env=model.base_url_env,
        region=model.region,
        lane=model.lane,
        preferred=model.preferred_endpoint,
        auth=model.auth,
        adapter=model.adapter,
        defaults=model.defaults,
        transport=model.transport,
        routing=model.routing,
        models={model.id: model},
    )


def resolve_request_for_model(
    model: Model,
    *,
    context: ProviderContext | None = None,
    options=None,
    env: dict[str, str] | None = None,
) -> ProviderRequest:
    if not isinstance(model, Model):
        raise TypeError("resolve_request_for_model model must be Model")
    identity = _concrete_model_identity(model)
    if identity is None:
        raise ValueError(
            f"Model {model.id!r} is not bound to a concrete provider endpoint"
        )
    provider_id, endpoint_id, api = identity
    resolved_env = dict(os.environ) if env is None else env
    base_url = _resolve_base_url(model, resolved_env)
    auth_view = resolve_auth_for_model(
        model,
        options=options,
        env=resolved_env,
    )
    defaults = dict(model.defaults)
    headers = dict(auth_view.headers)
    max_tokens = _resolve_max_tokens(options, defaults)
    reasoning_effort = _resolve_reasoning_effort(options, defaults)
    temperature = _resolve_temperature(options, defaults)
    return ProviderRequest(
        model=model,
        context=context or NormalizedContext(system_prompt=None),
        options=options,
        provider=provider_id,
        endpoint=endpoint_id,
        api=api,
        base_url=base_url,
        region=model.region,
        headers=headers,
        capabilities=model.capabilities,
        adapter_config=model.adapter or default_adapter_config(api),
        defaults=defaults,
        upstream_model_id=model.upstream_id or model.id,
        transport=model.transport,
        routing=model.routing,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
    )


def _concrete_model_identity(model: Model) -> tuple[str, str, str] | None:
    if not isinstance(model, Model):
        return None
    provider_id = model.provider_id
    endpoint_id = model.endpoint_id
    api = model.api
    if not provider_id or not endpoint_id or not isinstance(api, str) or not api:
        return None
    return provider_id, endpoint_id, api


def _resolve_base_url(
    model: Model,
    env: dict[str, str] | None,
) -> str:
    resolved_env = env or {}
    base_url_env = model.base_url_env
    if base_url_env and base_url_env in resolved_env:
        value = resolved_env[base_url_env]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Environment variable {base_url_env} must contain a non-empty base URL"
            )
        return _validate_resolved_base_url(value)
    base_url = model.base_url
    if base_url is None:
        if base_url_env:
            raise ValueError(
                f"Environment variable {base_url_env} is required for provider base URL"
            )
        raise ValueError(
            f"Model {model.id!r} has no configured provider base URL"
        )
    return _validate_resolved_base_url(_expand_env_template(base_url, resolved_env))


def _expand_env_template(value: str, env: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        replacement = env.get(name)
        if not isinstance(replacement, str) or not replacement.strip():
            raise ValueError(
                f"Environment variable {name} is required by baseUrl template"
            )
        return replacement

    return re.sub(r"\{([A-Z_][A-Z0-9_]*)\}", _replace, value)


def _validate_resolved_base_url(value: str) -> str:
    resolved = value.strip()
    if not resolved:
        raise ValueError("Provider base URL must be a non-empty string")
    if "{" in resolved or "}" in resolved:
        raise ValueError("Provider base URL contains an unresolved template")
    return resolved


def _resolve_max_tokens(options, defaults: dict[str, object]) -> int | None:
    value = get_max_output_tokens(options)
    if isinstance(value, int):
        return value
    if value is None:
        default_value = defaults.get("maxOutputTokens")
        if not isinstance(default_value, int):
            default_value = defaults.get("maxTokens")
        if isinstance(default_value, int):
            value = default_value
    return value if isinstance(value, int) else None


def _resolve_reasoning_effort(
    options,
    defaults: dict[str, Any],
) -> str | None:
    value = get_reasoning_effort(options)
    if value is None:
        default_value = defaults.get("reasoningEffort")
        if isinstance(default_value, str):
            value = default_value
    return value if isinstance(value, str) else None


def _resolve_temperature(options, defaults: dict[str, Any]) -> float | int | None:
    value = getattr(options, "temperature", None) if options is not None else None
    if value is None:
        default_value = defaults.get("temperature")
        if isinstance(default_value, int | float):
            value = default_value
    return value if isinstance(value, int | float) else None
