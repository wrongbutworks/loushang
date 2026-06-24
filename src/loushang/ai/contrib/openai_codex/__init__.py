from __future__ import annotations

from loushang.ai.api_registry import (
    ApiProviderRegistry,
    get_default_api_provider_registry,
)
from loushang.ai.auth.registry import OAuthProviderRegistry, get_default_oauth_registry
from loushang.ai.contrib.openai_codex.catalog import (
    OPENAI_CODEX_PROVIDER_ID,
    load_openai_codex_model_registry,
    register_openai_codex_models,
)
from loushang.ai.contrib.openai_codex.oauth import (
    AUTHORIZE_URL,
    CLIENT_ID,
    LOGIN_URL,
    REDIRECT_URI,
    TOKEN_URL,
    OpenAICodexOAuthProvider,
    register_openai_codex_oauth_provider,
)
from loushang.ai.contrib.openai_codex.options import OpenAICodexResponsesOptions
from loushang.ai.contrib.openai_codex.provider import OpenAICodexResponsesProvider
from loushang.ai.contrib.openai_codex.runtime_config import (
    OpenAICodexRuntimeConfig,
    resolve_openai_codex_runtime_config,
)
from loushang.ai.model import ModelRegistry, get_default_model_registry

OPENAI_CODEX_CONTRIB_SOURCE_ID = "contrib:openai-codex"


def register_openai_codex_contrib(
    *,
    api_registry: ApiProviderRegistry | None = None,
    oauth_registry: OAuthProviderRegistry | None = None,
    model_registry: ModelRegistry | None = None,
    source_id: str = OPENAI_CODEX_CONTRIB_SOURCE_ID,
) -> None:
    resolved_api_registry = api_registry or get_default_api_provider_registry()
    resolved_oauth_registry = oauth_registry or get_default_oauth_registry()
    resolved_model_registry = model_registry or get_default_model_registry()
    resolved_api_registry.register_api_provider(
        OpenAICodexResponsesProvider(),
        source_id=source_id,
    )
    register_openai_codex_oauth_provider(
        registry=resolved_oauth_registry,
        source_id=source_id,
    )
    register_openai_codex_models(registry=resolved_model_registry)


__all__ = [
    "AUTHORIZE_URL",
    "CLIENT_ID",
    "LOGIN_URL",
    "OPENAI_CODEX_CONTRIB_SOURCE_ID",
    "OPENAI_CODEX_PROVIDER_ID",
    "OpenAICodexOAuthProvider",
    "OpenAICodexResponsesOptions",
    "OpenAICodexResponsesProvider",
    "OpenAICodexRuntimeConfig",
    "REDIRECT_URI",
    "TOKEN_URL",
    "load_openai_codex_model_registry",
    "register_openai_codex_contrib",
    "register_openai_codex_models",
    "register_openai_codex_oauth_provider",
    "resolve_openai_codex_runtime_config",
]
