from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from loushang.ai.model import (
    Endpoint,
    Model,
    Provider,
    load_builtin_model_registry,
    load_model_registry_from_directory,
)
from loushang.ai.model.registry import (
    ModelRegistry as AiModelRegistry,
)
from loushang.ai.model.registry import (
    get_default_model_registry,
    resolve_model_ref,
)
from loushang.coding.types import ModelSelection
from loushang.observability import get_log

log = get_log(__name__).bind(component="ModelRegistry")


def _registry_provider_snapshot(
    registry: AiModelRegistry,
) -> dict[str, Provider]:
    return registry.providers


class ModelRegistry:
    def __init__(self, ai_registry: AiModelRegistry | None = None) -> None:
        self._ai_registry = (
            ai_registry if ai_registry is not None else get_default_model_registry()
        )
        self._ai_registry_consumers: list[object] = []

    @property
    def ai_registry(self) -> AiModelRegistry:
        return self._ai_registry

    def _bind_ai_registry_consumer(self, consumer: object) -> None:
        if all(bound is not consumer for bound in self._ai_registry_consumers):
            self._ai_registry_consumers.append(consumer)

    def _replace_ai_registry(self, registry: AiModelRegistry) -> None:
        previous = self._ai_registry
        self._ai_registry = registry
        retained_consumers: list[object] = []
        for consumer in self._ai_registry_consumers:
            if getattr(consumer, "ai_registry", None) is previous:
                setattr(consumer, "ai_registry", registry)
                retained_consumers.append(consumer)
        self._ai_registry_consumers = retained_consumers

    def reload(
        self,
        *,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        from loushang.ai.model.loader import _combine_model_registries

        sources = [("<builtin>", load_builtin_model_registry().providers)]
        for path in (user_dir, project_dir):
            if path is not None and path.is_dir():
                sources.append(
                    (str(path), load_model_registry_from_directory(path).providers)
                )
        self._replace_ai_registry(_combine_model_registries(sources))

    def register_model(self, model: Model) -> None:
        providers = _registry_provider_snapshot(self._ai_registry)
        provider = providers.get(model.provider_id) or Provider(id=model.provider_id)
        endpoint = provider.endpoints.get(model.endpoint_id) or Endpoint(
            id=model.endpoint_id,
            provider=model.provider_id,
            api=model.api or model.endpoint_id,
            base_url=model.base_url,
            base_url_env=model.base_url_env,
            region=model.region,
            lane=model.lane,
            preferred=model.preferred_endpoint,
            adapter=model.adapter,
            defaults=model.defaults,
        )
        models = dict(endpoint.models)
        models[model.id] = model
        endpoints = dict(provider.endpoints)
        endpoints[endpoint.id] = replace(endpoint, models=models)
        providers[provider.id] = replace(
            provider,
            endpoints=endpoints,
        )
        self._replace_ai_registry(AiModelRegistry.from_providers(providers))

    def register_provider(self, provider: Provider) -> None:
        providers = _registry_provider_snapshot(self._ai_registry)
        providers[provider.id] = provider
        self._replace_ai_registry(AiModelRegistry.from_providers(providers))

    def unregister_provider(self, provider_id: str) -> None:
        providers = _registry_provider_snapshot(self._ai_registry)
        providers.pop(provider_id, None)
        self._replace_ai_registry(AiModelRegistry.from_providers(providers))

    def get_model(self, name: str) -> ModelSelection | None:
        try:
            model = resolve_model_ref(self._ai_registry, name)
        except (KeyError, ValueError):
            return None
        return ModelSelection(provider=model.provider_id, model_id=model.id)

    def list_models(self) -> list[ModelSelection]:
        return [
            ModelSelection(provider=model.provider_id, model_id=model.id)
            for model in self._ai_registry.list_models()
        ]

    def resolve_model(
        self, selection_input: ModelSelection | str | Model
    ) -> ModelSelection:
        if isinstance(selection_input, ModelSelection):
            return selection_input
        if isinstance(selection_input, Model):
            return ModelSelection(
                provider=selection_input.provider_id, model_id=selection_input.id
            )

        model = resolve_model_ref(self._ai_registry, selection_input)
        return ModelSelection(provider=model.provider_id, model_id=model.id)

    def build_model(self, selection_input: ModelSelection | str | Model) -> Model:
        selection = self.resolve_model(selection_input)
        return self._resolve_model(selection)

    def _resolve_model(self, selection: ModelSelection) -> Model:
        if selection.endpoint_id:
            return self._ai_registry.get_model(
                selection.provider,
                selection.endpoint_id,
                selection.model_id,
            )
        try:
            return resolve_model_ref(
                self._ai_registry,
                f"{selection.provider}/{selection.model_id}",
            )
        except KeyError:
            log.problem(
                "model_selection_not_found",
                source="config",
                message=f"Model selection not found: {selection.provider}:{selection.model_id}",
                recoverable=True,
                provider_id=selection.provider,
                model_id=selection.model_id,
            )
            raise KeyError((selection.provider, selection.model_id))
        except ValueError as error:
            matches = self._ai_registry.list_models(
                provider=selection.provider,
                model_id=selection.model_id,
            )
            log.problem(
                "model_selection_ambiguous",
                source="config",
                message=f"Ambiguous model selection: {selection.provider}:{selection.model_id}",
                recoverable=True,
                provider_id=selection.provider,
                model_id=selection.model_id,
                endpoint_ids=[model.endpoint_id for model in matches],
            )
            raise ValueError(
                f"Ambiguous model selection: {selection.provider}:{selection.model_id}; {error}"
            ) from error
