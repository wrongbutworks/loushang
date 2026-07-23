"""Coding vocabulary bound to the shared session Work adapter."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from loushang.harness.agent_transcript import create_agent_transcript_message_codec
from loushang.harness.events import RuntimeEvent, project_session_runtime_event
from loushang.work.agent_projection import (
    AgentWorkFactProjectionContext,
    project_agent_event_to_work_facts,
)
from loushang.work.event_log import EventLogBackend
from loushang.work.session import (
    SessionPromptPort,
    SessionWorkProfile,
    SessionWorkRuntime,
)
from loushang.work.types import WorkEventFact

CODING_WORK_PROFILE = SessionWorkProfile(
    domain="coding",
    operation_kind="SubmitCodingTurn",
)

_MESSAGE_CODEC = create_agent_transcript_message_codec()


def create_coding_work_runtime(
    *,
    session: SessionPromptPort,
    event_log: EventLogBackend,
    session_id: Callable[[], str] = lambda: "",
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    cancellation_timeout: float | None = 30.0,
) -> SessionWorkRuntime:
    return SessionWorkRuntime(
        session=session,
        event_log=event_log,
        profile=CODING_WORK_PROFILE,
        project_event_facts=project_coding_runtime_event,
        session_id=session_id,
        clock=clock,
        cancellation_timeout=cancellation_timeout,
    )


def project_coding_runtime_event(event: object) -> Sequence[WorkEventFact]:
    if not isinstance(event, RuntimeEvent):
        return ()
    projected = project_session_runtime_event(event)
    if projected is None:
        return ()
    return project_agent_event_to_work_facts(
        projected,
        context=AgentWorkFactProjectionContext(
            source_event_ref=event.event_id,
            message_serializer=_MESSAGE_CODEC.serialize,
        ),
    )


__all__ = [
    "CODING_WORK_PROFILE",
    "create_coding_work_runtime",
    "project_coding_runtime_event",
]
