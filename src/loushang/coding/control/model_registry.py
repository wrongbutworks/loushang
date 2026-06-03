from __future__ import annotations

from pathlib import Path

from loushang.ai.model import Model, Provider
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.ai.model.registry import get_default_model_registry
from loushang.coding.types import ModelSelection
from loushang.observability import get_log

log = get_log(__name__).bind(component="ModelRegistry")


class ModelRegistry:
    def __init__(self, ai_registry: AiModelRegistry | None = None) -> None:
        self._ai_registry = ai_registry if ai_registry is not None else get_default_model_registry()

    @property
    def ai_registry(self) -> AiModelRegistry:
        return self._ai_registry

    def reload(
        self,
        *,
        user_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        from loushang.ai.model.loader import load_layered_model_registry

        self._ai_registry = load_layered_model_registry(
            user_dir=user_dir,
            project_dir=project_dir,
        )

    def register_model(self, model: Model) -> None:
        self._ai_registry.register_model(model)

    def register_provider(self, provider: Provider) -> None:
        self._ai_registry.register_provider(provider)

    def unregister_provider(self, provider_id: str) -> None:
        self._ai_registry.unregister_provider(provider_id)

    def get_model(self, name: str) -> ModelSelection | None:
        try:
            model = self._ai_registry.get_model(name)
        except (KeyError, ValueError):
            return None
        return ModelSelection(provider=model.provider_id, model_id=model.id)

    def list_models(self) -> list[ModelSelection]:
        return [
            ModelSelection(provider=model.provider_id, model_id=model.id)
            for model in self._ai_registry.list_models()
        ]

    def resolve_model(self, selection_input: ModelSelection | str | Model) -> ModelSelection:
        if isinstance(selection_input, ModelSelection):
            return selection_input
        if isinstance(selection_input, Model):
            return ModelSelection(provider=selection_input.provider_id, model_id=selection_input.id)

        model = self._ai_registry.get_model(selection_input)
        return ModelSelection(provider=model.provider_id, model_id=model.id)

    def build_model(self, selection_input: ModelSelection | str | Model) -> Model:
        selection = self.resolve_model(selection_input)
        return self._resolve_model(selection)

    def _resolve_model(self, selection: ModelSelection) -> Model:
        matches = [
            model
            for model in self._ai_registry.list_models(provider=selection.provider, model_id=selection.model_id)
        ]
        if not matches:
            log.problem(
                "model_selection_not_found",
                source="config",
                message=f"Model selection not found: {selection.provider}:{selection.model_id}",
                recoverable=True,
                provider_id=selection.provider,
                model_id=selection.model_id,
            )
            raise KeyError((selection.provider, selection.model_id))
        if len(matches) > 1:
            log.problem(
                "model_selection_ambiguous",
                source="config",
                message=f"Ambiguous model selection: {selection.provider}:{selection.model_id}",
                recoverable=True,
                provider_id=selection.provider,
                model_id=selection.model_id,
                endpoint_ids=[model.endpoint_id for model in matches],
            )
            raise ValueError(f"Ambiguous model selection: {selection.provider}:{selection.model_id}")
        return matches[0]
