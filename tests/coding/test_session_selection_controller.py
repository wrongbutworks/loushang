from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.ai.model import Capabilities, Model
from loushang.coding.session.types import ModelSelection
from loushang.coding.store import SessionManager


def _model(
    model_id: str = "faux-model",
    provider: str = "faux",
    *,
    reasoning: bool = True,
) -> Model:
    return Model(
        id=model_id,
        name=model_id,
        provider=provider,
        endpoint="responses",
        capabilities=Capabilities(
            reasoning=reasoning,
            input=("text",),
            context_window=128000,
            max_tokens=4096,
        ),
    )


class FakeModelRegistry:
    def __init__(self, models: list[Model]) -> None:
        self._models = models

    def list_models(self) -> list[ModelSelection]:
        return [
            ModelSelection(provider=model.provider_id, model_id=model.id)
            for model in self._models
        ]

    def build_model(self, selection: ModelSelection) -> Model:
        for model in self._models:
            if (
                model.provider_id == selection.provider
                and model.id == selection.model_id
            ):
                return model
        raise KeyError(selection)


class FakeExtensionRunner:
    def __init__(self) -> None:
        self.events: list[tuple[dict[str, object], str]] = []

    async def emit_event(self, event: dict[str, object], *, cwd: str) -> None:
        self.events.append((event, cwd))


def test_selection_controller_sets_model_records_auth_refresh_and_model_select(
    tmp_path,
) -> None:
    from loushang.coding.session.selection_controller import SelectionController

    first = _model()
    second = _model("alt-model", "alt")
    registry = FakeModelRegistry([first, second])
    runner = FakeExtensionRunner()
    auth_records: list[Model] = []
    refresh_reasons: list[str] = []
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
    controller = SelectionController(
        agent=Agent(
            initial_state={"system_prompt": "", "model": first, "thinking_level": "low"}
        ),
        session_manager=manager,
        get_model_registry=lambda: registry,
        get_extension_runner=lambda: runner,
        refresh_extension_runtime=lambda reason: _append_async(refresh_reasons, reason),
        is_extension_runtime_refreshing=lambda: False,
        record_model_auth_resolution=auth_records.append,
    )

    asyncio.run(
        controller.set_model(
            ModelSelection(provider="alt", model_id="alt-model"), emit_refresh=True
        )
    )

    assert controller.get_model_selection() == ModelSelection(
        provider="alt", model_id="alt-model"
    )
    assert manager.build_session_context().model == {
        "provider": "alt",
        "model_id": "alt-model",
    }
    assert auth_records == [second]
    assert refresh_reasons == ["model_selection_changed"]
    assert runner.events == [
        (
            {
                "type": "model_select",
                "model": second,
                "previous_model": first,
                "source": "set",
            },
            "/tmp/project",
        )
    ]


def test_selection_controller_records_explicit_endpoint_selection(tmp_path) -> None:
    from loushang.coding.session.selection_controller import SelectionController

    first = _model()
    second = _model("alt-model", "alt")
    registry = FakeModelRegistry([first, second])
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
    controller = SelectionController(
        agent=Agent(
            initial_state={
                "system_prompt": "",
                "model": first,
                "thinking_level": "low",
            }
        ),
        session_manager=manager,
        get_model_registry=lambda: registry,
        get_extension_runner=lambda: None,
        refresh_extension_runtime=lambda reason: _append_async([], reason),
        is_extension_runtime_refreshing=lambda: False,
        record_model_auth_resolution=lambda model: None,
    )

    asyncio.run(
        controller.set_model(
            ModelSelection(
                provider="alt",
                endpoint_id="responses",
                model_id="alt-model",
            ),
            emit_refresh=True,
        )
    )

    assert manager.build_session_context().model == {
        "provider": "alt",
        "model_id": "alt-model",
        "endpoint_id": "responses",
    }


def test_selection_controller_set_model_from_extension_respects_refresh_guard(
    tmp_path,
) -> None:
    from loushang.coding.session.selection_controller import SelectionController

    first = _model()
    second = _model("alt-model", "alt")
    registry = FakeModelRegistry([first, second])
    runner = FakeExtensionRunner()
    refresh_reasons: list[str] = []
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
    controller = SelectionController(
        agent=Agent(
            initial_state={"system_prompt": "", "model": first, "thinking_level": "low"}
        ),
        session_manager=manager,
        get_model_registry=lambda: registry,
        get_extension_runner=lambda: runner,
        refresh_extension_runtime=lambda reason: _append_async(refresh_reasons, reason),
        is_extension_runtime_refreshing=lambda: True,
        record_model_auth_resolution=lambda model: None,
    )

    asyncio.run(
        controller.set_model_from_extension(
            ModelSelection(provider="alt", model_id="alt-model")
        )
    )

    assert controller.get_model_selection() == ModelSelection(
        provider="alt", model_id="alt-model"
    )
    assert manager.build_session_context().model == {
        "provider": "alt",
        "model_id": "alt-model",
    }
    assert refresh_reasons == []
    assert runner.events == []


def test_selection_controller_cycles_scoped_model_and_thinking_level(tmp_path) -> None:
    from loushang.coding.session.selection_controller import SelectionController

    first = _model()
    second = _model("alt-model", "alt")
    registry = FakeModelRegistry([first, second])
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
    agent = Agent(
        initial_state={"system_prompt": "", "model": first, "thinking_level": "low"}
    )
    controller = SelectionController(
        agent=agent,
        session_manager=manager,
        get_model_registry=lambda: registry,
        get_extension_runner=lambda: None,
        refresh_extension_runtime=lambda reason: _append_async([], reason),
        is_extension_runtime_refreshing=lambda: False,
        record_model_auth_resolution=lambda model: None,
    )
    controller.set_scoped_models(
        [
            {"model": first, "thinkingLevel": "low"},
            {
                "model": {"provider": "alt", "model_id": "alt-model"},
                "thinkingLevel": "high",
            },
        ]
    )

    selection = asyncio.run(controller.cycle_model())

    assert selection == ModelSelection(provider="alt", model_id="alt-model")
    assert controller.get_model_selection() == ModelSelection(
        provider="alt", model_id="alt-model"
    )
    assert agent.thinking_level == "high"
    assert controller.get_scoped_models()[0]["model"] is first


def test_selection_controller_thinking_levels_follow_model_capability(tmp_path) -> None:
    from loushang.coding.session.selection_controller import SelectionController

    agent = Agent(
        initial_state={"system_prompt": "", "model": _model(), "thinking_level": "low"}
    )
    controller = SelectionController(
        agent=agent,
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
        get_model_registry=lambda: None,
        get_extension_runner=lambda: None,
        refresh_extension_runtime=lambda reason: _append_async([], reason),
        is_extension_runtime_refreshing=lambda: False,
        record_model_auth_resolution=lambda model: None,
    )

    assert controller.get_available_thinking_levels() == [
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert asyncio.run(controller.cycle_thinking_level()) == "medium"

    agent.model = _model("basic-model", "basic", reasoning=False)

    assert controller.get_available_thinking_levels() == ["off"]
    assert asyncio.run(controller.cycle_thinking_level()) is None
    assert agent.thinking_level == "off"


async def _append_async(values: list[str], value: str) -> None:
    values.append(value)
