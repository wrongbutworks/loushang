from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast

from loushang.harnesstui.conversation.agent_application import (
    AgentPlainConversationApplicationBinding,
    AgentScreenConversationApplicationBinding,
)
from loushang.harnesstui.conversation.host import (
    ConversationScreenRunProfile,
)
from loushang.harnesstui.conversation.startup import ConversationStartupView


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
