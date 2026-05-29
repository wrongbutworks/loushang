from __future__ import annotations

import asyncio

import pytest

from loushang.coding.session.extension_replacement_controller import ExtensionReplacementController


class Session:
    def __init__(self, name: str) -> None:
        self.name = name
        self.session_manager = f"manager:{name}"

    def create_replaced_session_context(self) -> str:
        return f"context:{self.name}"


class RuntimeHost:
    def __init__(self, before: Session, after: Session) -> None:
        self.current: Session = before
        self.after = after
        self.calls: list[tuple[str, object]] = []

    def get_current_session(self) -> Session:
        return self.current

    async def fork_session_with_result(self, entry_id: str, *, position: str = "at"):
        self.calls.append(("fork_with_result", (entry_id, position)))
        self.current = self.after
        return self.after, "selected text"

    async def new_session(self, *, parent_session: str | None = None) -> None:
        self.calls.append(("new_session", parent_session))
        self.current = self.after

    async def switch_session(self, session_path: str) -> None:
        self.calls.append(("switch_session", session_path))
        self.current = self.after


class CommandContext:
    def __init__(self, cwd: str) -> None:
        self._cwd = cwd
        self.invalidated = False

    @property
    def cwd(self) -> str:
        if self.invalidated:
            raise RuntimeError("stale context")
        return self._cwd


class Runner:
    def __init__(self) -> None:
        self.contexts: list[CommandContext] = []

    def create_command_context(self, *, fallback_cwd: str) -> CommandContext:
        context = CommandContext(fallback_cwd)
        self.contexts.append(context)
        return context


class ReplacedSession:
    def __init__(self, runner: Runner | None = None) -> None:
        self.extension_runner = runner
        self.session_manager = type("SessionManager", (), {"get_cwd": lambda self: "/tmp/project"})()
        self.messages: list[tuple[object, object | None]] = []
        self.user_messages: list[tuple[object, object | None]] = []

    async def _send_message_from_extension(self, message: object, options: object | None = None) -> None:
        self.messages.append((message, options))

    async def _send_user_message_from_extension_async(self, content: object, options: object | None = None) -> None:
        self.user_messages.append((content, options))


def test_extension_replacement_controller_forks_and_runs_with_session_callback() -> None:
    before = Session("before")
    after = Session("after")
    host = RuntimeHost(before, after)
    events: list[tuple[str, object]] = []

    async def _with_session(context):
        events.append(("withSession", context))

    controller = ExtensionReplacementController(get_runtime_host=lambda: host)

    result = asyncio.run(controller.fork("entry-1", {"position": "before", "withSession": _with_session}))

    assert result == {
        "cancelled": False,
        "selected_text": "selected text",
        "selectedText": "selected text",
    }
    assert host.calls == [("fork_with_result", ("entry-1", "before"))]
    assert events == [("withSession", "context:after")]


def test_extension_replacement_controller_new_session_runs_setup_before_with_session() -> None:
    before = Session("before")
    after = Session("after")
    host = RuntimeHost(before, after)
    events: list[tuple[str, object]] = []

    async def _setup(session_manager):
        events.append(("setup", session_manager))

    async def _with_session(context):
        events.append(("withSession", context))

    controller = ExtensionReplacementController(get_runtime_host=lambda: host)

    result = asyncio.run(
        controller.new_session(
            {
                "parentSession": "parent.jsonl",
                "setup": _setup,
                "withSession": _with_session,
            }
        )
    )

    assert result == {"cancelled": False}
    assert host.calls == [("new_session", "parent.jsonl")]
    assert events == [("setup", "manager:after"), ("withSession", "context:after")]


def test_extension_replacement_controller_reports_cancelled_without_runtime_host() -> None:
    controller = ExtensionReplacementController(get_runtime_host=lambda: None)

    assert asyncio.run(controller.fork("entry-1")) == {"cancelled": True}
    assert asyncio.run(controller.new_session()) == {"cancelled": True}
    assert asyncio.run(controller.switch_session("/tmp/session.jsonl")) == {"cancelled": True}


def test_extension_replacement_controller_validates_callbacks_and_fork_position() -> None:
    host = RuntimeHost(Session("before"), Session("after"))
    controller = ExtensionReplacementController(get_runtime_host=lambda: host)

    with pytest.raises(ValueError, match="Unsupported fork position"):
        asyncio.run(controller.fork("entry-1", {"position": "after"}))

    with pytest.raises(TypeError, match="withSession callback must be an async callable"):
        asyncio.run(controller.switch_session("/tmp/session.jsonl", {"withSession": lambda context: None}))


def test_extension_replacement_controller_creates_replaced_command_context() -> None:
    runner = Runner()
    session = ReplacedSession(runner)
    controller = ExtensionReplacementController(get_runtime_host=lambda: None)

    async def scenario() -> None:
        context = controller.create_context(session)
        assert context.cwd == "/tmp/project"

        await context.sendMessage({"customType": "demo"}, {"display": True})
        await context.send_message({"customType": "snake"}, None)
        await context.sendUserMessage("run this", {"deliverAs": "followUp"})
        await context.send_user_message("and this", None)

    asyncio.run(scenario())

    assert session.messages == [
        ({"customType": "demo"}, {"display": True}),
        ({"customType": "snake"}, None),
    ]
    assert session.user_messages == [
        ("run this", {"deliverAs": "followUp"}),
        ("and this", None),
    ]


def test_extension_replacement_controller_replaced_context_send_methods_obey_stale_guard() -> None:
    runner = Runner()
    session = ReplacedSession(runner)
    controller = ExtensionReplacementController(get_runtime_host=lambda: None)
    context = controller.create_context(session)
    context.invalidated = True

    with pytest.raises(RuntimeError, match="stale context"):
        asyncio.run(context.sendMessage({"customType": "demo"}, None))
    with pytest.raises(RuntimeError, match="stale context"):
        asyncio.run(context.sendUserMessage("run this", None))
