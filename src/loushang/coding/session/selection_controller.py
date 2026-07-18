from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from loushang.agent import Agent, ThinkingLevel
from loushang.ai.model import Model
from loushang.coding.session.types import ModelSelection
from loushang.coding.store import SessionManager

_THINKING_LEVEL_ORDER: tuple[ThinkingLevel, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
)


class _ModelRegistry(Protocol):
    def list_models(self) -> list[ModelSelection]: ...

    def build_model(self, selection: ModelSelection) -> Model: ...


class _ExtensionRunner(Protocol):
    async def emit_event(self, event: dict[str, object], *, cwd: str) -> None: ...


@dataclass
class SelectionController:
    agent: Agent
    session_manager: SessionManager
    get_model_registry: Callable[[], _ModelRegistry | None]
    get_extension_runner: Callable[[], _ExtensionRunner | None]
    refresh_extension_runtime: Callable[[str], Awaitable[None]]
    is_extension_runtime_refreshing: Callable[[], bool]
    _scoped_models: list[dict[str, object]] = field(default_factory=list)

    def get_model_selection(self) -> ModelSelection | None:
        model = self.agent.state.model
        return _selection_from_model(model)

    def get_available_models(self) -> list[ModelSelection]:
        registry = self.get_model_registry()
        if registry is None:
            return []
        return registry.list_models()

    def get_scoped_models(self) -> list[dict[str, object]]:
        return list(self._scoped_models)

    def set_scoped_models(self, scoped_models: list[dict[str, object]]) -> None:
        self._scoped_models = [dict(scoped) for scoped in scoped_models]

    async def set_model(
        self, model: Model | ModelSelection, *, emit_refresh: bool, source: str = "set"
    ) -> None:
        previous_model = self.agent.model
        resolved_model = self._resolve_model(model)
        explicit_endpoint_id = (
            model.endpoint_id if isinstance(model, ModelSelection) else None
        )
        await self._apply_model(resolved_model, endpoint_id=explicit_endpoint_id)
        if emit_refresh:
            await self.refresh_extension_runtime("model_selection_changed")
        runner = self.get_extension_runner()
        if runner is not None and not _models_are_equal(previous_model, resolved_model):
            await runner.emit_event(
                {
                    "type": "model_select",
                    "model": resolved_model,
                    "previous_model": previous_model,
                    "source": source,
                },
                cwd=self.session_manager.get_cwd(),
            )

    async def set_model_from_extension(self, selection: ModelSelection) -> None:
        resolved_model = self._resolve_model_from_selection(selection)
        await self._apply_model(resolved_model, endpoint_id=selection.endpoint_id)
        if not self.is_extension_runtime_refreshing():
            await self.refresh_extension_runtime("model_selection_changed")

    async def cycle_model(self, direction: str = "forward") -> ModelSelection | None:
        scoped_selection = await self.cycle_scoped_model(direction)
        if scoped_selection is not None:
            return scoped_selection
        models = self.get_available_models()
        if not isinstance(models, list):
            raise TypeError("Model registry returned an invalid response.")
        if not models:
            return None
        current = self.get_model_selection()
        try:
            index = models.index(current) if current is not None else -1
        except ValueError:
            index = -1
        selection = _cycle_selection(models, index, direction)
        await self.set_model(selection, emit_refresh=True, source="cycle")
        return selection

    async def cycle_scoped_model(self, direction: str) -> ModelSelection | None:
        if not self._scoped_models:
            return None
        selections: list[tuple[ModelSelection, ThinkingLevel | None]] = []
        for scoped in self._scoped_models:
            selection = self.model_selection_from_scoped_model(scoped)
            if selection is None:
                continue
            thinking_level = scoped.get("thinkingLevel") or scoped.get("thinking_level")
            selections.append(
                (selection, thinking_level if isinstance(thinking_level, str) else None)
            )
        if len(selections) <= 1:
            return None
        current = self.get_model_selection()
        try:
            index = (
                [selection for selection, _ in selections].index(current)
                if current is not None
                else -1
            )
        except ValueError:
            index = -1
        selection, thinking_level = _cycle_selection_pair(selections, index, direction)
        await self.set_model(selection, emit_refresh=True, source="cycle")
        if thinking_level is not None:
            await self.set_thinking_level(thinking_level)
        return selection

    def model_selection_from_scoped_model(
        self, scoped: dict[str, object]
    ) -> ModelSelection | None:
        model = scoped.get("model", scoped)
        if isinstance(model, ModelSelection):
            return model
        if isinstance(model, Model):
            return _selection_from_model(model)
        if isinstance(model, dict):
            provider = (
                model.get("provider")
                or model.get("provider_id")
                or model.get("providerId")
            )
            model_id = model.get("model_id") or model.get("modelId") or model.get("id")
            endpoint_id = (
                model.get("endpoint_id")
                or model.get("endpointId")
                or model.get("endpoint")
            )
            if isinstance(provider, str) and isinstance(model_id, str):
                return ModelSelection(
                    provider=provider,
                    model_id=model_id,
                    endpoint_id=endpoint_id if isinstance(endpoint_id, str) else None,
                )
        return None

    async def set_thinking_level(self, level: ThinkingLevel) -> None:
        available_levels = self.get_available_thinking_levels()
        effective_level = level if level in available_levels else available_levels[-1]
        if effective_level == self.agent.thinking_level:
            return
        await self.session_manager.append_thinking_level_change(effective_level)
        self.agent.thinking_level = effective_level

    async def cycle_thinking_level(self) -> ThinkingLevel | None:
        if not self.supports_thinking():
            await self.set_thinking_level("off")
            return None
        current = self.agent.state.thinking_level
        levels = self.get_available_thinking_levels()
        index = levels.index(current) if current in levels else 0
        next_level = levels[(index + 1) % len(levels)]
        await self.set_thinking_level(next_level)
        return next_level

    def supports_thinking(self) -> bool:
        return bool(getattr(self.agent.model, "reasoning", False))

    def supports_xhigh_thinking(self) -> bool:
        return self.supports_thinking()

    def get_available_thinking_levels(self) -> list[ThinkingLevel]:
        if not self.supports_thinking():
            return ["off"]
        return list(_THINKING_LEVEL_ORDER)

    def _resolve_model(self, model: Model | ModelSelection) -> Model:
        if isinstance(model, ModelSelection):
            return self._resolve_model_from_selection(model)
        return _validate_model(model)

    def _resolve_model_from_selection(self, selection: ModelSelection) -> Model:
        registry = self.get_model_registry()
        if registry is None:
            raise RuntimeError("ModelSelection requires a model registry")
        return _validate_model(registry.build_model(selection))

    async def _apply_model(
        self, model: Model, *, endpoint_id: str | None = None
    ) -> None:
        provider = getattr(model, "provider_id", None) or getattr(
            model, "provider", None
        )
        model_id = getattr(model, "id", None)
        if not provider or not model_id:
            raise ValueError("Model updates require a provider and model id.")
        await self.session_manager.append_model_change(
            str(provider),
            str(model_id),
            endpoint_id=endpoint_id,
        )
        self.agent.model = model


def _validate_model(model: object) -> Model:
    provider = getattr(model, "provider_id", None) or getattr(model, "provider", None)
    model_id = getattr(model, "id", None)
    if not provider or not model_id:
        raise ValueError("Model updates require a provider and model id.")
    return model  # type: ignore[return-value]


def _selection_from_model(model: object) -> ModelSelection | None:
    provider = getattr(model, "provider_id", None) or getattr(model, "provider", None)
    model_id = getattr(model, "id", None)
    if not provider or not model_id:
        return None
    return ModelSelection(provider=provider, model_id=model_id)


def _cycle_selection(
    models: list[ModelSelection], index: int, direction: str
) -> ModelSelection:
    if direction == "backward":
        return models[(index - 1) % len(models)]
    if direction == "forward":
        return models[(index + 1) % len(models)]
    raise ValueError("cycle_model direction must be 'forward' or 'backward'")


def _cycle_selection_pair(
    selections: list[tuple[ModelSelection, ThinkingLevel | None]],
    index: int,
    direction: str,
) -> tuple[ModelSelection, ThinkingLevel | None]:
    if direction == "backward":
        return selections[(index - 1) % len(selections)]
    if direction == "forward":
        return selections[(index + 1) % len(selections)]
    raise ValueError("cycle_model direction must be 'forward' or 'backward'")


def _models_are_equal(left: Model | None, right: Model | None) -> bool:
    if left is None or right is None:
        return left is right
    return (
        getattr(left, "provider_id", None) == getattr(right, "provider_id", None)
        and getattr(left, "endpoint_id", None) == getattr(right, "endpoint_id", None)
        and getattr(left, "id", None) == getattr(right, "id", None)
    )
