from __future__ import annotations

from loushang.ai.api_registry import (
    ApiProviderRegistry,
    get_default_api_provider_registry,
)
from loushang.ai.contrib.openai_codex.catalog import (
    OPENAI_CODEX_PROVIDER_ID,
    load_openai_codex_model_registry,
    register_openai_codex_models,
)
from loushang.ai.contrib.openai_codex.options import OpenAICodexResponsesOptions
from loushang.ai.contrib.openai_codex.provider import OpenAICodexResponsesProvider
from loushang.ai.contrib.openai_codex.runtime_config import OpenAICodexRuntimeConfig
from loushang.ai.model import ModelRegistry, get_default_model_registry

OPENAI_CODEX_CONTRIB_SOURCE_ID = "contrib:openai-codex"


def register_openai_codex_contrib(
    *,
    api_registry: ApiProviderRegistry | None = None,
    model_registry: ModelRegistry | None = None,
    source_id: str = OPENAI_CODEX_CONTRIB_SOURCE_ID,
) -> None:
    resolved_api_registry = api_registry or get_default_api_provider_registry()
    resolved_model_registry = model_registry or get_default_model_registry()
    resolved_api_registry.register_api_provider(
        OpenAICodexResponsesProvider(),
        source_id=source_id,
    )
    register_openai_codex_models(registry=resolved_model_registry)


__all__ = [
    "OPENAI_CODEX_CONTRIB_SOURCE_ID",
    "OPENAI_CODEX_PROVIDER_ID",
    "OpenAICodexResponsesOptions",
    "OpenAICodexResponsesProvider",
    "OpenAICodexRuntimeConfig",
    "load_openai_codex_model_registry",
    "register_openai_codex_contrib",
    "register_openai_codex_models",
]
