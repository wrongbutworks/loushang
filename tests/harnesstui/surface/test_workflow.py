from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loushang.harness.commands import CommandDef, CommandKind
from loushang.harnesstui.settings.workflow import SettingsApplyResult
from loushang.harnesstui.status.line import StatusLineSettings
from loushang.harnesstui.surface.controller import ApprovalSurfaceDecision
from loushang.harnesstui.surface.view import ScreenSurfaceView
from loushang.harnesstui.surface.workflow import (
    ScreenSurfaceCommand,
    ScreenSurfaceWorkflow,
    ScreenSurfaceWorkflowCopy,
    ScreenSurfaceWorkflowPorts,
)
from loushang.tui import InfoPanel, InputIntent, SurfaceHost


@dataclass(slots=True)
class _App:
    active_surface: object | None = None
    surface_host: SurfaceHost | None = None


class _Catalog:
    def __init__(self) -> None:
        self.definitions = {
            name: CommandDef(
                id=f"product.{name}",
                name=name,
                kind=CommandKind.LOCAL_UI,
            )
            for name in (
                "model",
                "models",
                "command",
                "commands",
                "terminal",
                "hotkeys",
                "settings",
            )
        }

    def lookup(self, text: str) -> CommandDef | None:
        name = text.strip().split(maxsplit=1)[0].removeprefix("/")
        return self.definitions.get(name)

    def commands(self) -> tuple[CommandDef, ...]:
        return tuple(self.definitions.values())


@dataclass(slots=True)
class _State:
    statuses: list[str] = field(default_factory=list)
    command_texts: list[str] = field(default_factory=list)
    model_values: list[str] = field(default_factory=list)
    approvals: list[ApprovalSurfaceDecision | None] = field(default_factory=list)
    statusline_visible: list[bool] = field(default_factory=list)
    statusline_settings: list[StatusLineSettings] = field(default_factory=list)
    model_refreshes: int = 0
    renders: int = 0
    fail_model: bool = False
    accept_approval: bool = True


class _SettingsPage:
    async def apply_setting(self, item_id: str, value: str) -> SettingsApplyResult:
        assert (item_id, value) == ("model.current", "provider/beta")
        return SettingsApplyResult(
            "selected",
            statusline_settings=StatusLineSettings(style="muted"),
            refresh_model_label=True,
        )


def _surface(title: str, purpose: str) -> ScreenSurfaceView:
    return ScreenSurfaceView(
        title=title,
        purpose=purpose,  # type: ignore[arg-type]
        content=InfoPanel(title=title, text="body"),
        presentation="bottom-exclusive",
    )


def _normalize(text: str, command: CommandDef) -> ScreenSurfaceCommand:
    query = text.strip().partition(" ")[2]
    kinds = {
        "model": "select_model",
        "models": "list_models",
        "command": "select_command",
        "commands": "list_commands",
        "terminal": "terminal_diagnostics",
        "hotkeys": "hotkeys",
        "settings": "settings",
    }
    if command.name == "command" and query:
        query = f"/{query.removeprefix('/')}"
    return ScreenSurfaceCommand(kinds[command.name], query)  # type: ignore[arg-type]


def _workflow(*, state: _State | None = None) -> tuple[ScreenSurfaceWorkflow, _State]:
    state = state or _State()

    async def select_model(value: str) -> str:
        state.model_values.append(value)
        if state.fail_model:
            raise RuntimeError("catalog offline")
        return f"selected:{value}"

    async def refresh_model() -> None:
        state.model_refreshes += 1

    async def format_models(query: str) -> str:
        return f"models:{query}"

    async def format_commands(query: str) -> str:
        return f"commands:{query}"

    async def model_selector() -> ScreenSurfaceView:
        return _surface("Choose model", "model")

    async def command_selector() -> ScreenSurfaceView:
        return _surface("Choose command", "command")

    async def settings_content() -> object:
        return _SettingsPage()

    async def decide_approval(
        decision: ApprovalSurfaceDecision | None,
    ) -> bool | None:
        state.approvals.append(decision)
        return state.accept_approval

    workflow = ScreenSurfaceWorkflow(
        app=_App(),
        ports=ScreenSurfaceWorkflowPorts(
            select_model=select_model,
            refresh_model_label=refresh_model,
            set_command_text=state.command_texts.append,
            set_status=state.statuses.append,
            set_statusline_visible=state.statusline_visible.append,
            set_statusline_settings=state.statusline_settings.append,
            request_render=lambda: setattr(state, "renders", state.renders + 1),
            command_catalog=_Catalog(),
            normalize_command=_normalize,
            format_models=format_models,
            models_info_body=lambda text: f"body<{text}>",
            format_commands=format_commands,
            build_model_selector=model_selector,
            build_command_selector=command_selector,
            build_settings_content=settings_content,
            terminal_diagnostics=lambda: "terminal body",
            hotkeys=lambda: "hotkeys body",
            decide_approval=decide_approval,
        ),
        copy=ScreenSurfaceWorkflowCopy(
            recoverable_error=lambda error: f"recoverable:{error}",
            command_selected=lambda command: f"command:{command}",
            approval_stale="stale",
            approval_confirmed=lambda action: f"approved:{action}",
            approval_rejected="rejected",
            models_title="Models title",
            commands_title="Commands title",
            terminal_title="Terminal title",
            hotkeys_title="Hotkeys title",
            settings_title="Settings title",
        ),
    )
    return workflow, state


def test_surface_workflow_routes_product_normalized_commands_and_copy() -> None:
    workflow, state = _workflow()

    assert workflow.is_local_command("/missing") is False
    assert workflow.is_local_command("/command inspect") is True
    asyncio.run(workflow.handle_text("/command inspect"))

    assert state.command_texts == ["/inspect "]
    assert state.statuses == ["command:/inspect"]

    asyncio.run(workflow.handle_text("/models beta"))
    surface = workflow.current
    assert isinstance(surface, ScreenSurfaceView)
    assert surface.title == "Models title"
    assert surface.presentation == "bottom-exclusive"
    assert isinstance(surface.content, InfoPanel)
    assert surface.content.text == "body<models:beta>"

    asyncio.run(workflow.handle_text("/terminal"))
    surface = workflow.current
    assert isinstance(surface, ScreenSurfaceView)
    assert surface.title == "Terminal title"
    assert isinstance(surface.content, InfoPanel)
    assert surface.content.text == "terminal body"


def test_surface_workflow_applies_model_and_keeps_recoverable_error_surface_open() -> None:
    state = _State(fail_model=True)
    workflow, _ = _workflow(state=state)
    asyncio.run(workflow.handle_text("/model"))
    model_surface = workflow.current

    asyncio.run(
        workflow.handle_surface_intent(
            InputIntent(kind="select", text="provider/beta")
        )
    )

    assert workflow.current is model_surface
    assert state.statuses == ["recoverable:catalog offline"]
    assert state.model_refreshes == 0

    state.fail_model = False
    asyncio.run(
        workflow.handle_surface_intent(
            InputIntent(kind="select", text="provider/beta")
        )
    )

    assert workflow.current is None
    assert state.statuses[-1] == "selected:provider/beta"
    assert state.model_refreshes == 1


def test_surface_workflow_applies_settings_effects_without_closing_page() -> None:
    workflow, state = _workflow()
    asyncio.run(workflow.handle_text("/settings"))
    settings_surface = workflow.current

    asyncio.run(
        workflow.handle_surface_intent(
            InputIntent(kind="setting", text="model.current", note="provider/beta")
        )
    )

    assert workflow.current is settings_surface
    assert state.statusline_settings == [StatusLineSettings(style="muted")]
    assert state.model_refreshes == 1
    assert state.renders == 1


def test_surface_workflow_adapts_approval_decision_and_product_status_copy() -> None:
    state = _State(accept_approval=False)
    workflow, _ = _workflow(state=state)
    workflow.open_approval(action="delete cache", action_id="approval-1")

    asyncio.run(workflow.handle_surface_intent(InputIntent(kind="approve")))

    assert state.approvals == [
        ApprovalSurfaceDecision(
            action_id="approval-1",
            action="delete cache",
            approved=True,
            raw_note="approval-1",
        )
    ]
    assert state.statuses == ["stale"]
    assert workflow.current is None
