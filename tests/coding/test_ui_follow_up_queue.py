from __future__ import annotations

import asyncio


class _Lifecycle:
    active_id = 7

    def __init__(self, *, active: bool) -> None:
        self.active = active


class _Renderer:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def render_status(self, text: str) -> None:
        self.statuses.append(text)


class _Controller:
    def __init__(self, result) -> None:
        self.result = result
        self.follow_ups: list[str] = []

    async def follow_up(self, text: str):
        self.follow_ups.append(text)
        return self.result


def test_follow_up_queue_ignores_empty_text() -> None:
    from loushang.coding.ui.controller import ControllerResult
    from loushang.coding.ui.follow_up_queue import FollowUpQueueHandler

    renderer = _Renderer()
    controller = _Controller(ControllerResult())
    traces: list[str] = []

    handler = FollowUpQueueHandler(
        lifecycle=_Lifecycle(active=True),
        controller=controller,
        renderer=renderer,
        emit=lambda write, *, label: _emit(write),
        trace=lambda name, **_data: traces.append(name),
    )

    result = asyncio.run(handler.queue("   ", source="keybinding"))

    assert result is None
    assert controller.follow_ups == []
    assert renderer.statuses == []
    assert traces == ["prompt.follow_up.start", "prompt.follow_up.ignored"]


def test_follow_up_queue_reports_idle_follow_up_as_unavailable() -> None:
    from loushang.coding.ui.controller import ControllerResult
    from loushang.coding.ui.follow_up_queue import FollowUpQueueHandler

    renderer = _Renderer()
    controller = _Controller(ControllerResult())
    emitted: list[str] = []

    async def emit(write, *, label: str) -> None:
        emitted.append(label)
        write()

    handler = FollowUpQueueHandler(
        lifecycle=_Lifecycle(active=False),
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=lambda _name, **_data: None,
    )

    result = asyncio.run(handler.queue("next", source="command"))

    assert result is None
    assert controller.follow_ups == []
    assert emitted == ["follow_up:idle"]
    assert renderer.statuses == ["Follow-up is only available while a run is active."]


def test_follow_up_queue_strips_and_queues_active_follow_up() -> None:
    from loushang.coding.ui.controller import ControllerResult
    from loushang.coding.ui.follow_up_queue import FollowUpQueueHandler

    renderer = _Renderer()
    controller = _Controller(ControllerResult(exit_code=3))
    emitted: list[str] = []

    async def emit(write, *, label: str) -> None:
        emitted.append(label)
        write()

    handler = FollowUpQueueHandler(
        lifecycle=_Lifecycle(active=True),
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=lambda _name, **_data: None,
    )

    result = asyncio.run(handler.queue("  next step  ", source="keybinding"))

    assert result == 3
    assert controller.follow_ups == ["next step"]
    assert emitted == ["follow_up:queued"]
    assert renderer.statuses == ["Follow-up queued."]


def test_follow_up_queue_renders_controller_error() -> None:
    from loushang.coding.ui.controller import ControllerResult
    from loushang.coding.ui.follow_up_queue import FollowUpQueueHandler

    renderer = _Renderer()
    controller = _Controller(ControllerResult(exit_code=2, error_message="queue failed"))
    emitted: list[str] = []

    async def emit(write, *, label: str) -> None:
        emitted.append(label)
        write()

    handler = FollowUpQueueHandler(
        lifecycle=_Lifecycle(active=True),
        controller=controller,
        renderer=renderer,
        emit=emit,
        trace=lambda _name, **_data: None,
    )

    result = asyncio.run(handler.queue("next", source="command"))

    assert result == 2
    assert controller.follow_ups == ["next"]
    assert emitted == ["follow_up:error"]
    assert renderer.statuses == ["queue failed"]


async def _emit(write) -> None:
    write()
