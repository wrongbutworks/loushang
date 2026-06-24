from __future__ import annotations

from importlib.resources import as_file, files

from loushang.ai.model import (
    ModelRegistry,
    get_default_model_registry,
    load_model_registry_from_file,
)

OPENAI_CODEX_PROVIDER_ID = "openai-codex"


def load_openai_codex_model_registry() -> ModelRegistry:
    resource = files("loushang.ai.contrib.openai_codex").joinpath("models.json")
    with as_file(resource) as path:
        return load_model_registry_from_file(path)


def register_openai_codex_models(
    *,
    registry: ModelRegistry | None = None,
) -> None:
    resolved_registry = registry or get_default_model_registry()
    contrib_registry = load_openai_codex_model_registry()
    provider = contrib_registry.get_provider(OPENAI_CODEX_PROVIDER_ID)
    if provider is None:
        raise RuntimeError("OpenAI Codex contrib catalog is missing its provider")
    resolved_registry.register_provider(provider)


__all__ = [
    "OPENAI_CODEX_PROVIDER_ID",
    "load_openai_codex_model_registry",
    "register_openai_codex_models",
]
