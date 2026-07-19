from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from loushang.agent import Agent, ThinkingLevel
from loushang.ai.model import Model, ModelSelection
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import AgentTranscriptSelectionRuntime


class _ModelRegistry(Protocol):
    def list_models(self) -> list[ModelSelection]: ...

    def build_model(self, selection: ModelSelection) -> Model: ...


class _ExtensionRunner(Protocol):
    async def emit_event(self, event: dict[str, object], *, cwd: str) -> None: ...


@dataclass
class SelectionController:
    """Coding policy adapter over the Harness transcript selection runtime."""

    agent: Agent
    session_manager: SessionManager
    get_model_registry: Callable[[], _ModelRegistry | None]
    get_extension_runner: Callable[[], _ExtensionRunner | None]
    refresh_extension_runtime: Callable[[str], Awaitable[None]]
    is_extension_runtime_refreshing: Callable[[], bool]
    _runtime: AgentTranscriptSelectionRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._runtime = AgentTranscriptSelectionRuntime(
            session=self.session_manager,
            get_model=lambda: self.agent.model,
            set_model=lambda model: setattr(self.agent, "model", model),
            get_thinking_level=lambda: self.agent.thinking_level,
            set_thinking_level_value=lambda level: setattr(
                self.agent, "thinking_level", level
            ),
            get_model_catalog=self.get_model_registry,
        )

    def get_model_selection(self) -> ModelSelection | None:
        return self._runtime.get_model_selection()

    def get_available_models(self) -> list[ModelSelection]:
        return self._runtime.get_available_models()

    def get_scoped_models(self) -> list[dict[str, object]]:
        return self._runtime.get_scoped_models()

    def set_scoped_models(self, scoped_models: list[dict[str, object]]) -> None:
        self._runtime.set_scoped_models(scoped_models)

    async def set_model(
        self,
        model: Model | ModelSelection,
        *,
        emit_refresh: bool,
        source: str = "set",
    ) -> None:
        previous_model = self.agent.model
        resolved_model = self._runtime.resolve_model(model)
        endpoint_id = model.endpoint_id if isinstance(model, ModelSelection) else None
        await self._runtime.apply_model(resolved_model, endpoint_id=endpoint_id)
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
        resolved_model = self._runtime.resolve_model(selection)
        await self._runtime.apply_model(
            resolved_model,
            endpoint_id=selection.endpoint_id,
        )
        if not self.is_extension_runtime_refreshing():
            await self.refresh_extension_runtime("model_selection_changed")

    async def cycle_model(self, direction: str = "forward") -> ModelSelection | None:
        scoped_selection = await self.cycle_scoped_model(direction)
        if scoped_selection is not None:
            return scoped_selection
        selection = self._runtime.cycle_model_selection(direction)
        if selection is None:
            return None
        await self.set_model(selection, emit_refresh=True, source="cycle")
        return selection

    async def cycle_scoped_model(self, direction: str) -> ModelSelection | None:
        selected = self._runtime.cycle_scoped_selection(direction)
        if selected is None:
            return None
        selection, thinking_level = selected
        await self.set_model(selection, emit_refresh=True, source="cycle")
        if thinking_level is not None:
            await self.set_thinking_level(thinking_level)
        return selection

    def model_selection_from_scoped_model(
        self,
        scoped: dict[str, object],
    ) -> ModelSelection | None:
        return self._runtime.model_selection_from_scoped_model(scoped)

    async def set_thinking_level(self, level: ThinkingLevel) -> None:
        await self._runtime.set_thinking_level(level)

    async def cycle_thinking_level(self) -> ThinkingLevel | None:
        return await self._runtime.cycle_thinking_level()

    def supports_thinking(self) -> bool:
        return self._runtime.supports_thinking()

    def supports_xhigh_thinking(self) -> bool:
        return self.supports_thinking()

    def get_available_thinking_levels(self) -> list[ThinkingLevel]:
        return self._runtime.get_available_thinking_levels()


def _models_are_equal(left: Model | None, right: Model | None) -> bool:
    if left is None or right is None:
        return left is right
    return (
        getattr(left, "provider_id", None) == getattr(right, "provider_id", None)
        and getattr(left, "endpoint_id", None) == getattr(right, "endpoint_id", None)
        and getattr(left, "id", None) == getattr(right, "id", None)
    )
