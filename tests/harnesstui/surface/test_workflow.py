from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace

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
from loushang.tui import InfoPanel, InputIntent, RenderRequestKind, SurfaceHost


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
    resumed_sessions: list[str] = field(default_factory=list)
    statusline_visible: list[bool] = field(default_factory=list)
    statusline_settings: list[StatusLineSettings] = field(default_factory=list)
    model_refreshes: int = 0
    renders: int = 0
    fail_model: bool = False
    accept_approval: bool = True


@dataclass(slots=True)
class _Composer:
    state: _State

    def set_text(self, text: str) -> None:
        self.state.command_texts.append(text)


@dataclass(slots=True)
class _App:
    state: _State
    active_surface: object | None = None
    surface_host: SurfaceHost | None = None
    composer: _Composer = field(init=False)

    def __post_init__(self) -> None:
        self.composer = _Composer(self.state)

    def set_status(self, message: str | None) -> None:
        if message is not None:
            self.state.statuses.append(message)

    def set_statusline_visible(self, visible: bool) -> None:
        self.state.statusline_visible.append(visible)

    def set_statusline_settings(self, settings: StatusLineSettings) -> None:
        self.state.statusline_settings.append(settings)

    def request_render(self, kind: RenderRequestKind = "product") -> None:
        assert kind == "product"
        self.state.renders += 1


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

    def resume_surface() -> ScreenSurfaceView:
        return _surface("Resume session", "session")

    async def activate_continuity(target: object) -> str:
        reference = str(target)
        state.resumed_sessions.append(reference)
        return f"resumed:{reference}"

    async def decide_approval(
        decision: ApprovalSurfaceDecision | None,
    ) -> bool | None:
        state.approvals.append(decision)
        return state.accept_approval

    workflow = ScreenSurfaceWorkflow(
        app=_App(state),
        ports=ScreenSurfaceWorkflowPorts(
            select_model=select_model,
            refresh_model_label=refresh_model,
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
            normalize_interactive_command=lambda text: (
                ScreenSurfaceCommand("resume_session")
                if text.strip() == "/resume"
                else None
            ),
            build_resume_surface=resume_surface,
            activate_continuity=activate_continuity,
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


def test_surface_workflow_applies_model_and_keeps_recoverable_error_surface_open() -> (
    None
):
    state = _State(fail_model=True)
    workflow, _ = _workflow(state=state)
    asyncio.run(workflow.handle_text("/model"))
    model_surface = workflow.current

    asyncio.run(
        workflow.handle_surface_intent(InputIntent(kind="select", text="provider/beta"))
    )

    assert workflow.current is model_surface
    assert state.statuses == ["recoverable:catalog offline"]
    assert state.model_refreshes == 0

    state.fail_model = False
    asyncio.run(
        workflow.handle_surface_intent(InputIntent(kind="select", text="provider/beta"))
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


def test_surface_workflow_opens_resume_picker_and_submits_reference() -> None:
    workflow, state = _workflow()

    assert workflow.is_local_command("/resume") is True
    assert workflow.is_local_command("/resume abc123") is False
    asyncio.run(workflow.handle_text("/resume"))

    picker = workflow.current
    assert isinstance(picker, ScreenSurfaceView)
    assert picker.purpose == "session"

    asyncio.run(
        workflow.handle_surface_intent(
            InputIntent(kind="select", text="/tmp/session.jsonl")
        )
    )

    assert state.resumed_sessions == ["/tmp/session.jsonl"]
    assert state.statuses == ["resumed:/tmp/session.jsonl"]
    assert workflow.current is None


def test_surface_workflow_runs_continuity_activation_without_freezing_page() -> None:
    class _ActivationContent:
        selected_target = "typed-target"

        def __init__(self) -> None:
            self.activating = False
            self.closed = False
            self.failure: Exception | None = None

        def begin_activation(self) -> bool:
            if self.activating:
                return False
            self.activating = True
            return True

        def fail_activation(self, error: Exception) -> None:
            self.activating = False
            self.failure = error

        def close(self) -> None:
            self.closed = True

    async def scenario() -> None:
        workflow, state = _workflow()
        gate = asyncio.Event()

        async def activate(target: object) -> str:
            assert target == "typed-target"
            await gate.wait()
            return "resumed:typed-target"

        workflow.ports = replace(workflow.ports, activate_continuity=activate)
        content = _ActivationContent()
        picker = ScreenSurfaceView(
            title="Resume",
            purpose="session",
            content=content,
            presentation="page",
        )
        workflow.open(picker)

        await workflow.handle_surface_intent(
            InputIntent(kind="select", text="opaque-render-value")
        )

        assert workflow.current is picker
        assert content.activating is True
        assert state.statuses == []

        gate.set()
        task = workflow._session_activation_task
        assert task is not None
        await task

        assert workflow.current is None
        assert content.closed is True
        assert state.statuses == ["resumed:typed-target"]

    asyncio.run(scenario())


def test_surface_workflow_keeps_continuity_failure_visible_on_page() -> None:
    class _ActivationContent:
        selected_target = "typed-target"

        def __init__(self) -> None:
            self.failure: Exception | None = None

        def begin_activation(self) -> bool:
            return True

        def fail_activation(self, error: Exception) -> None:
            self.failure = error

    async def scenario() -> None:
        workflow, state = _workflow()

        async def fail(_target: object) -> str:
            raise RuntimeError("restore failed")

        workflow.ports = replace(workflow.ports, activate_continuity=fail)
        content = _ActivationContent()
        picker = ScreenSurfaceView(
            title="Resume",
            purpose="session",
            content=content,
            presentation="page",
        )
        workflow.open(picker)

        await workflow.handle_surface_intent(
            InputIntent(kind="select", text="opaque-render-value")
        )
        task = workflow._session_activation_task
        assert task is not None
        await task

        assert workflow.current is picker
        assert isinstance(content.failure, RuntimeError)
        assert state.statuses == ["recoverable:restore failed"]

    asyncio.run(scenario())


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
