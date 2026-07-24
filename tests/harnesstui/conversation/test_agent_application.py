from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast

from loushang.ai.model import ModelSelection
from loushang.harness.commands import CommandDescriptor
from loushang.harnesstui.conversation.agent_application import (
    AgentPlainConversationApplicationBinding,
    AgentScreenConversationApplicationBinding,
    bind_agent_screen_approval_presenter,
    bind_agent_screen_session_transition,
    build_agent_screen_surface_workflow_ports,
    current_agent_runtime_session,
    handle_agent_screen_approval,
)
from loushang.harnesstui.conversation.host import (
    ConversationScreenRunProfile,
)
from loushang.harnesstui.conversation.startup import ConversationStartupView
from loushang.harnesstui.surface.controller import ApprovalSurfaceDecision


class _Manager:
    def get_branch(self) -> tuple[object, ...]:
        return ()


class _Session:
    session_manager = _Manager()
    settings_manager = None
    session_id = "research-session"

    def get_tool_definition(self, _name: str) -> None:
        return None

    def get_steering_messages(self) -> tuple[str, ...]:
        return ()

    def get_follow_up_messages(self) -> tuple[str, ...]:
        return ()

    def get_thinking_level(self) -> str:
        return "medium"


class _Surface:
    async def handle_text(self, _text: str) -> None:
        return None

    async def handle_surface_intent(self, _intent: object) -> None:
        return None

    def is_local_command(self, _text: str) -> bool:
        return False

    def clear_approval_surfaces(self) -> None:
        return None


def _startup() -> ConversationStartupView:
    return ConversationStartupView(
        model_label="research/model",
        cwd="/research",
        branch="main",
        project_label="research",
        session_label="Research",
        session_observability_id="research-session",
    )


def test_agent_screen_application_binding_prepares_shared_state() -> None:
    session = _Session()

    class App:
        state = SimpleNamespace(running=False)

        def set_statusline_settings(self, settings: object) -> None:
            self.settings = settings

    app = App()
    statuses: list[object] = []
    traces: list[tuple[str, dict[str, object]]] = []
    binding = AgentScreenConversationApplicationBinding(
        session=session,
        app=cast(Any, app),
        action_host=cast(Any, object()),
        build_surface=lambda status: statuses.append(status) or _Surface(),
        startup=_startup(),
        interaction_context=cast(Any, nullcontext()),
        profile=ConversationScreenRunProfile(
            input_router_factory=None,
            interruption_message="Interrupted",
            cancellation_message="Cancelled",
        ),
        trace=lambda name, **data: traces.append((name, data)),
        stdout=cast(Any, SimpleNamespace(write=lambda _value: None)),
        now=lambda: 1.0,
        resume_command_prefix=("research", "--resume"),
    )

    prepared = binding.prepare()

    assert prepared.app is app
    assert prepared.event_source is session
    assert prepared.history_records == ()
    assert prepared.should_exit("/quit") is True
    assert prepared.should_exit("continue") is False
    assert len(statuses) == 1
    prepared.on_start()
    assert traces == [
        (
            "tui.start",
            {
                "interactive": True,
                "model": "research/model",
                "cwd": "/research",
                "branch": "main",
                "session": "Research",
            },
        )
    ]


def test_agent_screen_surface_ports_bind_structural_research_session() -> None:
    labels: list[str] = []
    approvals: list[dict[str, object]] = []

    class ResearchSession:
        def get_model_selection(self) -> ModelSelection:
            return ModelSelection(provider="research", model_id="analyst")

        def get_available_models(self) -> tuple[ModelSelection, ...]:
            return (
                ModelSelection(provider="research", model_id="analyst"),
                ModelSelection(provider="research", model_id="reviewer"),
            )

        async def list_commands(self) -> tuple[CommandDescriptor[object], ...]:
            return (
                CommandDescriptor(
                    name="report",
                    description="Build a research report",
                    source="research",
                ),
            )

    async def select_model(value: str) -> str:
        return f"Selected {value}"

    async def build_settings_content() -> object:
        return {"product": "research"}

    async def on_approval(event: dict[str, object]) -> bool:
        approvals.append(event)
        return True

    ports = build_agent_screen_surface_workflow_ports(
        ResearchSession(),
        select_model=select_model,
        set_model_label=labels.append,
        build_settings_content=build_settings_content,
        terminal_diagnostics=lambda: "research terminal",
        hotkeys=lambda: "research hotkeys",
        on_approval=on_approval,
    )

    assert asyncio.run(ports.format_commands("report")) == (
        "Commands:\n/report - Build a research report (research)"
    )
    assert "research/analyst" in asyncio.run(ports.format_models(""))
    assert asyncio.run(ports.build_model_selector()).purpose == "model"
    assert asyncio.run(ports.build_command_selector()).purpose == "command"
    assert asyncio.run(ports.build_settings_content()) == {"product": "research"}
    asyncio.run(ports.refresh_model_label())
    assert labels == ["research/analyst"]

    assert ports.decide_approval is not None
    assert asyncio.run(
        ports.decide_approval(
            ApprovalSurfaceDecision(
                action_id="research-approval",
                action="Publish report",
                approved=True,
                raw_note="approved",
            )
        )
    )
    assert approvals == [
        {
            "action_id": "research-approval",
            "action": "Publish report",
            "approved": True,
            "raw_note": "approved",
        }
    ]


def test_agent_screen_approval_binding_uses_structural_product_ports() -> None:
    presented: list[dict[str, object]] = []
    cleared: list[str] = []
    subscriptions: list[object] = []

    class Session:
        presenter: object | None = None

        def set_approval_presenter(
            self,
            presenter: object | None,
            *,
            dismisser: object | None = None,
        ) -> None:
            self.presenter = presenter
            self.dismisser = dismisser

        async def handle_screen_approval(self, event: dict[str, object]) -> bool:
            return event.get("approved") is True

    class Surface:
        def open_approval(self, **payload: object) -> None:
            presented.append(payload)

        def dismiss_approval(self, action_id: str) -> None:
            presented.append({"dismissed": action_id})

        def clear_approval_surfaces(self) -> None:
            cleared.append("cleared")

    class Runtime:
        current_session: object | None

        def __init__(self, session: object) -> None:
            self.current_session = session

        def subscribe_after_session_invalidate(self, callback: object):
            subscriptions.append(callback)
            return lambda: subscriptions.append("unsubscribed")

    session = Session()
    surface = Surface()
    runtime = Runtime(session)
    unbind_presenter = bind_agent_screen_approval_presenter(
        session,
        surface,
        default_action="Approve operation",
    )
    unbind_transition = bind_agent_screen_session_transition(runtime, surface)

    assert callable(session.presenter)
    session.presenter({"action_id": "approval-1"})  # type: ignore[operator]
    assert presented == [
        {
            "action": "Approve operation",
            "risk": "",
            "action_id": "approval-1",
        }
    ]
    assert asyncio.run(handle_agent_screen_approval(session, {"approved": True}))
    assert current_agent_runtime_session(runtime, object()) is session
    assert callable(subscriptions[0])
    subscriptions[0]()  # type: ignore[operator]
    assert cleared == ["cleared"]

    unbind_transition()
    unbind_presenter()
    assert subscriptions[-1] == "unsubscribed"
    assert session.presenter is None


def test_agent_plain_application_binding_prepares_projection_and_header() -> None:
    session = _Session()
    headers: list[dict[str, object]] = []
    app = object()
    renderer = SimpleNamespace(
        render_header=lambda **kwargs: headers.append(kwargs),
    )
    binding = AgentPlainConversationApplicationBinding(
        session=session,
        renderer=cast(Any, renderer),
        startup=_startup(),
        interaction_context=cast(Any, nullcontext()),
        build_app=lambda _event_renderer, _emit: cast(Any, app),
        trace=lambda _name, **_data: None,
    )

    prepared = binding.prepare()
    prepared.render_header()

    assert prepared.event_source is session
    assert prepared.build_app(cast(Any, lambda *_args, **_kwargs: None)) is app
    assert headers == [
        {
            "project_label": "research",
            "cwd": "/research",
            "branch": "main",
            "session_label": "Research",
            "model_label": "research/model",
        }
    ]
