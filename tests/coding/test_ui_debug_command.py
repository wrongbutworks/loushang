from __future__ import annotations

import asyncio
from pathlib import Path


class _Renderer:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def render_status(self, text: str) -> None:
        self.statuses.append(text)


def test_debug_command_handler_disables_debug_logging() -> None:
    from loushang.coding.ui.debug_command import DebugCommandHandler
    from loushang.coding.ui.intent import DebugIntent

    renderer = _Renderer()
    emitted: list[str] = []
    traces: list[str] = []
    disabled = False

    async def emit(write, *, label: str) -> None:
        emitted.append(label)
        write()

    def disable() -> None:
        nonlocal disabled
        disabled = True

    handler = DebugCommandHandler(
        session=object(),
        cwd="/repo",
        renderer=renderer,
        emit=emit,
        trace=lambda name, **_data: traces.append(name),
        enable=lambda **_kwargs: Path("/tmp/debug.log"),
        disable=disable,
    )

    result = asyncio.run(handler.handle(DebugIntent(enabled=False)))

    assert result is None
    assert disabled is True
    assert emitted == ["debug:disabled"]
    assert renderer.statuses == ["Debug logging disabled."]
    assert traces == ["debug.disabled"]


def test_debug_command_handler_enables_debug_logging_with_scopes() -> None:
    from loushang.coding.ui.debug_command import DebugCommandHandler
    from loushang.coding.ui.intent import DebugIntent

    session = object()
    renderer = _Renderer()
    emitted: list[str] = []
    traces: list[tuple[str, dict[str, object]]] = []
    captured: dict[str, object] = {}
    debug_path = Path("/repo/.loushang/debug/session.log")

    async def emit(write, *, label: str) -> None:
        emitted.append(label)
        write()

    def enable(*, session, scopes):
        captured["session"] = session
        captured["scopes"] = scopes
        return debug_path

    handler = DebugCommandHandler(
        session=session,
        cwd="/repo",
        renderer=renderer,
        emit=emit,
        trace=lambda name, **data: traces.append((name, data)),
        enable=enable,
        disable=lambda: None,
    )

    result = asyncio.run(handler.handle(DebugIntent(enabled=True, scopes=("tui", "agent"))))

    assert result is None
    assert captured == {"session": session, "scopes": ("tui", "agent")}
    assert emitted == ["debug:enabled"]
    assert "Debug logging enabled:" in renderer.statuses[0]
    assert "Scopes: tui,agent" in renderer.statuses[0]
    assert traces == [("debug.enabled", {"path": str(debug_path), "scopes": ["tui", "agent"]})]
