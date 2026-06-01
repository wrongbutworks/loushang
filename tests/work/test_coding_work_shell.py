from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime


class FakePromptSession:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events
        self.prompts: list[str] = []
        self.listeners: list[Callable[[dict[str, object]], Awaitable[None] | None]] = []

    def subscribe(self, listener: Callable[[dict[str, object]], Awaitable[None] | None]) -> Callable[[], None]:
        self.listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    async def prompt(self, text: str) -> None:
        self.prompts.append(text)
        for event in self.events:
            for listener in list(self.listeners):
                result = listener(event)
                if result is not None:
                    await result


def test_coding_work_shell_wraps_prompt_and_logs_operation_run_and_projected_events() -> None:
    from loushang.work import CodingWorkShell, InMemoryEventLogBackend

    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = FakePromptSession(
            events=[
                {
                    "type": "message_update",
                    "message": {"role": "assistant"},
                    "assistant_message_event": {"type": "text_delta", "text": "done"},
                },
                {
                    "type": "tool_execution_end",
                    "tool_call_id": "tool-1",
                    "tool_name": "pytest",
                    "result": {"output": "passed"},
                    "is_error": False,
                },
            ],
        )
        shell = CodingWorkShell(
            session=session,
            event_log=event_log,
            clock=lambda: datetime(2026, 6, 1, 10, 30, tzinfo=UTC),
        )

        run = await shell.submit_coding_turn(
            "fix this bug",
            session_id="session-1",
            operation_id="op-1",
            run_id="run-1",
        )

        assert session.prompts == ["fix this bug"]
        assert run.status == "completed"
        assert len(session.listeners) == 0

        entries = event_log.query(run_id="run-1")
        assert [entry.entry_type for entry in entries] == ["operation", "event", "event", "event", "event"]
        assert entries[0].payload == {
            "kind": "SubmitCodingTurn",
            "domain": "coding",
            "payload": {"text": "fix this bug"},
        }
        assert [entry.payload["kind"] for entry in entries[1:]] == [
            "WorkRunStarted",
            "ContentDelta",
            "ToolCallCompleted",
            "WorkRunCompleted",
        ]
        assert entries[2].payload["delivery_hint"] == "coalesce"
        assert entries[3].payload["delivery_hint"] == "coalesce"
        assert entries[4].payload["delivery_hint"] == "immediate"

    asyncio.run(scenario())
