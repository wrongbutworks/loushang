"""Coding's Work and event binding for the shared plain host."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal, TextIO

from loushang.coding.event import (
    SUPPORTED_JSON_EVENT_VIEWS,
    project_runtime_event_to_json_views,
    project_session_event,
    should_emit_projected_event,
    should_emit_runtime_event_view,
)
from loushang.coding.work_executor import SubmitCodingTurn
from loushang.coding.work_runtime import CodingWorkRuntime
from loushang.coding.work_shell import CodingWorkShell
from loushang.harness.events import normalize_event_select
from loushang.harnesstui.conversation.plain_mode import (
    PlainEventProjection,
    PlainHost,
    PlainWorkPort,
)
from loushang.work import EventLogBackend

_EVENT_PROJECTION = PlainEventProjection(
    supported_views=SUPPORTED_JSON_EVENT_VIEWS,
    normalize_select=normalize_event_select,
    project_session_event=project_session_event,
    should_emit_projected_event=should_emit_projected_event,
    project_runtime_event_to_json_views=project_runtime_event_to_json_views,
    should_emit_runtime_event_view=should_emit_runtime_event_view,
)


class _CodingWorkPort(PlainWorkPort):
    def __init__(
        self,
        *,
        session: Any,
        event_log: EventLogBackend,
        coding_runtime: CodingWorkRuntime | None,
    ) -> None:
        self._session = session
        self._event_log = event_log
        self._coding_runtime = coding_runtime

    def _shell(self) -> CodingWorkShell:
        return CodingWorkShell(
            session=self._session,
            event_log=self._event_log,
            coding_runtime=self._coding_runtime,
        )

    async def submit_turn(
        self,
        text: str,
        *,
        session_id: str,
        images: list[object] | None,
        include_work_metadata: bool,
        method_id: str | None,
        plan_id: str | None,
        step_id: str | None,
        step_index: int | None,
        step_title: str | None,
        planned_constraint: Mapping[str, object] | None,
        audit_policy: Mapping[str, object] | None,
        plan_facts: Mapping[str, object] | None,
        step_facts: Mapping[str, object] | None,
    ) -> None:
        await self._shell().submit_coding_turn(
            text,
            session_id=session_id,
            images=images,
            method_id=method_id if include_work_metadata else None,
            plan_id=plan_id if include_work_metadata else None,
            step_id=step_id if include_work_metadata else None,
            step_index=step_index if include_work_metadata else None,
            step_title=step_title if include_work_metadata else None,
            planned_constraint=planned_constraint if include_work_metadata else None,
            audit_policy=audit_policy if include_work_metadata else None,
            plan_facts=plan_facts if include_work_metadata else None,
            step_facts=step_facts if include_work_metadata else None,
        )

    async def submit_plan(
        self,
        turns: Sequence[object],
        *,
        session_id: str,
        after_turn: Callable[[object, int, int], Awaitable[None]],
    ) -> None:
        await self._shell().submit_coding_plan(
            turns,
            session_id=session_id,
            after_turn=after_turn,
            wait_for_idle_after_prompt=True,
        )


class PrintMode(PlainHost):
    """Coding Product adapter over the shared HarnessTUI plain host."""

    def __init__(
        self,
        *,
        runtime: Any,
        session: Any,
        stdout: TextIO,
        stderr: TextIO | None = None,
        output_mode: Literal["text", "json"] = "text",
        event_view: str = "full",
        event_select: Sequence[str] | str | None = None,
        render_tool_events: bool = False,
        work_event_log: EventLogBackend | None = None,
        coding_work_runtime: CodingWorkRuntime | None = None,
        method_id: str | None = None,
        plan_id: str | None = None,
        step_id: str | None = None,
        step_index: int | None = None,
        step_title: str | None = None,
        planned_constraint: Mapping[str, object] | None = None,
        audit_policy: Mapping[str, object] | None = None,
        plan_facts: Mapping[str, object] | None = None,
        step_facts: Mapping[str, object] | None = None,
    ) -> None:
        work_port = (
            _CodingWorkPort(
                session=session,
                event_log=work_event_log,
                coding_runtime=coding_work_runtime,
            )
            if work_event_log is not None
            else None
        )
        super().__init__(
            runtime=runtime,
            session=session,
            stdout=stdout,
            stderr=stderr,
            output_mode=output_mode,
            event_view=event_view,
            event_select=event_select,
            render_tool_events=render_tool_events,
            work_event_log=work_event_log,
            work_port=work_port,
            event_projection=_EVENT_PROJECTION,
            method_id=method_id,
            plan_id=plan_id,
            step_id=step_id,
            step_index=step_index,
            step_title=step_title,
            planned_constraint=planned_constraint,
            audit_policy=audit_policy,
            plan_facts=plan_facts,
            step_facts=step_facts,
        )


async def run_print_mode(
    *,
    runtime: Any,
    session: Any,
    user_input: str,
    stdout: TextIO,
    stderr: TextIO | None = None,
    images: list[object] | None = None,
    follow_up_messages: Sequence[str] = (),
    output_mode: Literal["text", "json"] = "text",
    event_view: str = "full",
    event_select: Sequence[str] | str | None = None,
    render_tool_events: bool = False,
    work_event_log: EventLogBackend | None = None,
    coding_work_runtime: CodingWorkRuntime | None = None,
    method_id: str | None = None,
    plan_id: str | None = None,
    step_id: str | None = None,
    step_index: int | None = None,
    step_title: str | None = None,
    planned_constraint: Mapping[str, object] | None = None,
    audit_policy: Mapping[str, object] | None = None,
    plan_facts: Mapping[str, object] | None = None,
    step_facts: Mapping[str, object] | None = None,
    dispose: bool = True,
) -> int:
    mode = PrintMode(
        runtime=runtime,
        session=session,
        stdout=stdout,
        stderr=stderr,
        output_mode=output_mode,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
        method_id=method_id,
        plan_id=plan_id,
        step_id=step_id,
        step_index=step_index,
        step_title=step_title,
        planned_constraint=planned_constraint,
        audit_policy=audit_policy,
        plan_facts=plan_facts,
        step_facts=step_facts,
    )
    return await mode.run_once(
        user_input,
        images=images,
        follow_up_messages=follow_up_messages,
        dispose=dispose,
    )


async def run_print_plan_mode(
    *,
    runtime: Any,
    session: Any,
    turns: Sequence[SubmitCodingTurn],
    stdout: TextIO,
    stderr: TextIO | None = None,
    output_mode: Literal["text", "json"] = "text",
    event_view: str = "full",
    event_select: Sequence[str] | str | None = None,
    render_tool_events: bool = False,
    work_event_log: EventLogBackend,
    coding_work_runtime: CodingWorkRuntime | None = None,
    dispose: bool = True,
) -> int:
    mode = PrintMode(
        runtime=runtime,
        session=session,
        stdout=stdout,
        stderr=stderr,
        output_mode=output_mode,
        event_view=event_view,
        event_select=event_select,
        render_tool_events=render_tool_events,
        work_event_log=work_event_log,
        coding_work_runtime=coding_work_runtime,
    )
    return await mode.run_plan(turns, dispose=dispose)


__all__ = ["PrintMode", "run_print_mode", "run_print_plan_mode"]
