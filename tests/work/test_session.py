from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from loushang.work import InMemoryEventLogBackend
from loushang.work.session import (
    SessionWorkProfile,
    SessionWorkRuntime,
    SessionWorkTurn,
)


class _DesignSession:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def subscribe_runtime_events(
        self,
        listener: Callable[[object], object],
    ) -> Callable[[], None]:
        del listener
        return lambda: None

    async def prompt(self, text: str) -> None:
        self.prompts.append(text)


def test_session_work_runtime_accepts_product_vocabulary_as_a_profile() -> None:
    async def scenario() -> None:
        event_log = InMemoryEventLogBackend()
        session = _DesignSession()
        runtime = SessionWorkRuntime(
            session=session,
            event_log=event_log,
            profile=SessionWorkProfile(
                domain="design",
                operation_kind="SubmitDesignTurn",
            ),
            project_event_facts=lambda _event: (),
            clock=lambda: datetime(2026, 7, 23, tzinfo=UTC),
        )

        run = await runtime.submit_turn(
            SessionWorkTurn(text="revise the title slide"),
            session_id="design-session",
            operation_id="design-operation",
            run_id="design-run",
        )

        assert run.status == "completed"
        assert session.prompts == ["revise the title slide"]
        operation = event_log.query(run_id="design-run")[0]
        assert operation.payload == {
            "kind": "SubmitDesignTurn",
            "domain": "design",
            "payload": {"text": "revise the title slide"},
        }

    asyncio.run(scenario())
