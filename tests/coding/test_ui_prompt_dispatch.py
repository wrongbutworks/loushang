from __future__ import annotations

import asyncio


class _Lifecycle:
    def __init__(self) -> None:
        self.active = False
        self.active_id = 0
        self.begin_calls = 0
        self.end_calls = 0

    def begin_work(self) -> int:
        self.begin_calls += 1
        self.active = True
        self.active_id += 1
        return self.active_id

    def end_work(self) -> None:
        self.end_calls += 1
        self.active = False


class _Controller:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.intents: list[object] = []

    async def dispatch(self, intent):
        self.intents.append(intent)
        if self.error is not None:
            raise self.error
        return self.result


def test_prompt_dispatch_begins_and_ends_work_intents() -> None:
    from loushang.coding.ui.controller import ControllerResult
    from loushang.coding.ui.intent import PromptIntent
    from loushang.coding.ui.prompt_dispatch import PromptDispatchHandler

    lifecycle = _Lifecycle()
    result = ControllerResult()
    traces: list[tuple[str, dict[str, object]]] = []
    intent = PromptIntent("hello")

    handler = PromptDispatchHandler(
        lifecycle=lifecycle,
        controller=_Controller(result),
        session_running=lambda: False,
        trace=lambda name, **data: traces.append((name, data)),
    )

    outcome = asyncio.run(handler.dispatch(intent))

    assert outcome.result is result
    assert outcome.run_id == 1
    assert outcome.work_intent is True
    assert lifecycle.begin_calls == 1
    assert lifecycle.end_calls == 1
    assert lifecycle.active is False
    assert traces == [
        ("prompt.dispatch.start", {"intent": "PromptIntent", "work_intent": True, "run_id": 1}),
        ("prompt.dispatch.end", {"run_id": 1, "active_run": False, "session_running": False}),
    ]


def test_prompt_dispatch_does_not_start_lifecycle_for_non_work_intents() -> None:
    from loushang.coding.ui.controller import ControllerResult
    from loushang.coding.ui.intent import QuitIntent
    from loushang.coding.ui.prompt_dispatch import PromptDispatchHandler

    lifecycle = _Lifecycle()
    intent = QuitIntent()

    handler = PromptDispatchHandler(
        lifecycle=lifecycle,
        controller=_Controller(ControllerResult(exit_code=0)),
        session_running=lambda: True,
        trace=lambda _name, **_data: None,
    )

    outcome = asyncio.run(handler.dispatch(intent))

    assert outcome.run_id is None
    assert outcome.work_intent is False
    assert outcome.result.exit_code == 0
    assert lifecycle.begin_calls == 0
    assert lifecycle.end_calls == 0


def test_prompt_dispatch_ends_work_when_controller_raises() -> None:
    from loushang.coding.ui.intent import BashIntent
    from loushang.coding.ui.prompt_dispatch import PromptDispatchHandler

    lifecycle = _Lifecycle()
    error = RuntimeError("dispatch exploded")

    handler = PromptDispatchHandler(
        lifecycle=lifecycle,
        controller=_Controller(error=error),
        session_running=lambda: False,
        trace=lambda _name, **_data: None,
    )

    try:
        asyncio.run(handler.dispatch(BashIntent("pwd")))
    except RuntimeError as caught:
        assert caught is error
    else:
        raise AssertionError("expected RuntimeError")

    assert lifecycle.begin_calls == 1
    assert lifecycle.end_calls == 1
    assert lifecycle.active is False
