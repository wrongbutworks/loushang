"""Content-free, aggregate timing for the startup of one Agent turn."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from loushang.agent.types import AgentEvent, ModelCallPreparation
from loushang.ai.prepared_request import PreparedModelRequest
from loushang.foundation.json import JSONValue
from loushang.foundation.observability import get_log

NanosecondClock = Callable[[], int]
TurnIdFactory = Callable[[], str]

_TURN_START_PERFORMANCE_LOG = get_log(__name__).bind(component="TurnStart")


class TurnPerformanceLog(Protocol):
    def debug_event(self, scope: str, name: str, **data: JSONValue) -> None: ...


@dataclass
class _TurnTimingState:
    turn_id: str
    source: str
    started_ns: int
    milestones: dict[str, int] = field(default_factory=dict)
    invocation_id: str | None = None
    attempt: int | None = None
    purpose: str | None = None
    provider_id: str | None = None
    endpoint_id: str | None = None
    api_id: str | None = None
    model_id: str | None = None
    outcome_hint: str | None = None
    queued: bool = False
    active: bool = False
    finished: bool = False


class TurnStartPerformanceHandle:
    """Own timing for one submitted prompt without retaining its content."""

    def __init__(
        self,
        runtime: TurnStartPerformanceRuntime,
        state: _TurnTimingState,
    ) -> None:
        self._runtime = runtime
        self._state = state

    def mark(self, milestone: str) -> None:
        self._runtime._mark(self._state, milestone)

    def activate(self) -> None:
        self._runtime._activate(self._state)

    def mark_queued(self) -> None:
        self._state.queued = True
        self.mark("queued")

    def finish(self, outcome: str) -> None:
        self._runtime._finish(self._state, outcome=outcome)


class TurnStartPerformanceRuntime:
    """Correlate prompt, Agent, Model Input, and first-response milestones."""

    def __init__(
        self,
        *,
        session_id: str,
        clock: NanosecondClock = time.perf_counter_ns,
        turn_id_factory: TurnIdFactory = lambda: uuid4().hex,
        log: TurnPerformanceLog = _TURN_START_PERFORMANCE_LOG,
    ) -> None:
        self._session_id = session_id
        self._clock = clock
        self._turn_id_factory = turn_id_factory
        self._log = log
        self._active: _TurnTimingState | None = None

    def begin(self, *, source: str | None) -> TurnStartPerformanceHandle:
        started_ns = self._clock()
        state = _TurnTimingState(
            turn_id=self._turn_id_factory(),
            source=_source_category(source),
            started_ns=started_ns,
            milestones={"submission_received": started_ns},
        )
        return TurnStartPerformanceHandle(self, state)

    def observe_agent_event(self, event: AgentEvent) -> None:
        state = self._active_state()
        if state is None:
            return
        event_type = event.get("type")
        if event_type == "turn_start":
            self._mark(state, "agent_loop_started")
            return
        if event_type in {"message_start", "message_update", "turn_end"}:
            message = event.get("message")
            if getattr(message, "role", None) != "assistant":
                return
            if event_type == "message_start":
                self._mark(state, "first_response")
            elif event_type == "message_update":
                assistant_event = event.get("assistant_message_event")
                if (
                    isinstance(assistant_event, dict)
                    and assistant_event.get("type")
                    in {
                        "text_delta",
                        "thinking_delta",
                        "toolcall_delta",
                        "image_end",
                    }
                ):
                    self._mark(state, "first_content")
            _capture_outcome_hint(state, message)
            return
        if event_type == "agent_end":
            messages = event.get("messages")
            if isinstance(messages, list | tuple) and messages:
                _capture_outcome_hint(state, messages[-1])

    def model_call_prepare_started(self, preparation: ModelCallPreparation) -> None:
        state = self._active_state()
        if state is None:
            return
        self._mark(state, "model_call_prepare_started")
        if state.purpose is None:
            state.purpose = _purpose_category(preparation.purpose)
        model = preparation.model
        if state.provider_id is None:
            state.provider_id = model.provider_id
            state.endpoint_id = model.endpoint_id
            state.api_id = model.api
            state.model_id = model.id

    def model_call_prepared(self) -> None:
        state = self._active_state()
        if state is not None:
            self._mark(state, "model_call_prepared")

    def model_call_prepare_failed(self) -> None:
        state = self._active_state()
        if state is not None:
            state.outcome_hint = "failed"
            self._mark(state, "model_call_prepare_failed")

    def model_input_commit_started(self, request: PreparedModelRequest) -> None:
        state = self._active_state()
        if state is None:
            return
        self._capture_request(state, request)
        self._mark(state, "model_input_commit_started")

    def transport_ready(self, request: PreparedModelRequest) -> None:
        state = self._active_state()
        if state is None:
            return
        self._capture_request(state, request)
        self._mark(state, "transport_ready")

    def model_input_commit_failed(self, request: PreparedModelRequest) -> None:
        state = self._active_state()
        if state is None:
            return
        self._capture_request(state, request)
        state.outcome_hint = "failed"
        self._mark(state, "model_input_commit_failed")

    def _capture_request(
        self,
        state: _TurnTimingState,
        request: PreparedModelRequest,
    ) -> None:
        if state.invocation_id is not None:
            return
        state.invocation_id = request.invocation_id
        state.attempt = request.attempt
        state.provider_id = request.provider_id
        state.endpoint_id = request.endpoint_id
        state.api_id = request.api
        state.model_id = request.model_id

    def _active_state(self) -> _TurnTimingState | None:
        state = self._active
        if state is None or state.finished:
            return None
        return state

    def _activate(self, state: _TurnTimingState) -> None:
        if state.finished:
            return
        active = self._active_state()
        if active is not None and active is not state:
            state.outcome_hint = "contended"
            return
        self._active = state
        state.active = True
        self._mark(state, "agent_run_dispatched")

    def _mark(self, state: _TurnTimingState, milestone: str) -> None:
        if state.finished or milestone in state.milestones:
            return
        state.milestones[milestone] = self._clock()

    def _finish(self, state: _TurnTimingState, *, outcome: str) -> None:
        if state.finished:
            return
        self._mark(state, "finished")
        state.finished = True
        if self._active is state:
            self._active = None
        resolved_outcome = state.outcome_hint or ("queued" if state.queued else outcome)
        self._emit(state, outcome=resolved_outcome)

    def _emit(self, state: _TurnTimingState, *, outcome: str) -> None:
        try:
            finished_ns = state.milestones.get("finished", self._clock())
            startup_ns = _first_available_milestone(
                state.milestones,
                "first_content",
                "first_response",
            )
            local_ready_ns = state.milestones.get("transport_ready")
            self._log.debug_event(
                "turn.start.performance",
                "turn",
                schema_version=1,
                session_id=self._session_id,
                turn_id=state.turn_id,
                source=state.source,
                outcome=outcome,
                queued=state.queued,
                invocation_id=state.invocation_id,
                attempt=state.attempt,
                purpose=state.purpose,
                provider_id=state.provider_id,
                endpoint_id=state.endpoint_id,
                api_id=state.api_id,
                model_id=state.model_id,
                total_ms=_milliseconds(finished_ns - state.started_ns),
                startup_ms=(
                    _milliseconds(startup_ns - state.started_ns)
                    if startup_ns is not None
                    else None
                ),
                local_ready_ms=(
                    _milliseconds(local_ready_ns - state.started_ns)
                    if local_ready_ns is not None
                    else None
                ),
                milestones=_milestone_data(state),
                phases=_phase_data(state),
            )
        except Exception:
            return


def _capture_outcome_hint(state: _TurnTimingState, message: object) -> None:
    stop_reason = getattr(message, "stop_reason", None)
    error_message = getattr(message, "error_message", None)
    if stop_reason == "aborted":
        state.outcome_hint = "cancelled"
    elif stop_reason == "error" or error_message:
        state.outcome_hint = "failed"


def _source_category(source: str | None) -> str:
    if source is None:
        return "interactive"
    if source in {"tui", "rpc", "extension", "interactive"}:
        return source
    if source.startswith("multiagent:"):
        return "multiagent"
    return "other"


def _purpose_category(purpose: str) -> str:
    if purpose in {
        "main",
        "continuation",
        "retry",
        "side_question",
        "compaction_history",
        "branch_summary",
        "compaction_turn_prefix",
        "compaction_merge",
    }:
        return purpose
    return "other"


def _first_available_milestone(
    milestones: Mapping[str, int],
    *names: str,
) -> int | None:
    for name in names:
        value = milestones.get(name)
        if value is not None:
            return value
    return None


def _milestone_data(state: _TurnTimingState) -> dict[str, JSONValue]:
    return {
        name: {"elapsed_ms": _milliseconds(timestamp - state.started_ns)}
        for name, timestamp in state.milestones.items()
    }


def _phase_data(state: _TurnTimingState) -> dict[str, JSONValue]:
    phases: dict[str, JSONValue] = {}
    _add_phase(
        phases,
        state,
        "input_pipeline",
        "submission_received",
        "agent_run_dispatched",
    )
    _add_phase(
        phases,
        state,
        "agent_to_model_call",
        "agent_run_dispatched",
        "model_call_prepare_started",
    )
    _add_phase(
        phases,
        state,
        "model_call_prepare",
        "model_call_prepare_started",
        "model_call_prepared",
    )
    _add_phase(
        phases,
        state,
        "model_input_commit",
        "model_input_commit_started",
        "transport_ready",
    )
    _add_phase(
        phases,
        state,
        "provider_first_response",
        "transport_ready",
        "first_response",
    )
    _add_phase(
        phases,
        state,
        "provider_first_content",
        "transport_ready",
        "first_content",
    )
    return phases


def _add_phase(
    phases: dict[str, JSONValue],
    state: _TurnTimingState,
    name: str,
    started: str,
    finished: str,
) -> None:
    started_ns = state.milestones.get(started)
    finished_ns = state.milestones.get(finished)
    if started_ns is None or finished_ns is None:
        return
    phases[name] = {"total_ms": _milliseconds(max(0, finished_ns - started_ns))}


def _milliseconds(duration_ns: int) -> float:
    return round(duration_ns / 1_000_000, 3)


__all__ = ["TurnStartPerformanceHandle", "TurnStartPerformanceRuntime"]
