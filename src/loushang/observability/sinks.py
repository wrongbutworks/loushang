from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Protocol

from .context import LogContext, current_context
from .problem import JSONValue, ProblemRecord


@dataclass(frozen=True)
class DebugEventRecord:
    scope: str
    name: str
    data: dict[str, JSONValue] = field(default_factory=dict)
    time: str = ""
    monotonic_ms: int = 0
    module: str | None = None
    component: str | None = None
    session_id: str | None = None
    run_id: int | str | None = None
    cwd: str | None = None
    mode: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        return asdict(self)


class DebugLogSinkProtocol(Protocol):
    def write_log(
        self,
        *,
        level: str,
        module: str,
        component: str | None,
        message: str,
        context: LogContext,
        details: dict[str, JSONValue],
    ) -> None: ...

    def write_problem(self, record: ProblemRecord) -> None: ...

    def write_debug_event(self, record: DebugEventRecord) -> None: ...


class TraceSinkProtocol(Protocol):
    def write_problem(self, record: ProblemRecord) -> None: ...

    def write_debug_event(self, record: DebugEventRecord) -> None: ...


class InMemoryProblemStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: list[ProblemRecord] = []

    def record(self, record: ProblemRecord) -> None:
        with self._lock:
            self._records.append(record)

    def record_problem(self, record: ProblemRecord) -> None:
        self.record(record)

    def all(self) -> list[ProblemRecord]:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


@dataclass
class _ObservabilityConfig:
    problem_store: InMemoryProblemStore = field(default_factory=InMemoryProblemStore)
    debug_sink: DebugLogSinkProtocol | None = None
    trace_sink: TraceSinkProtocol | None = None
    debug_scopes: frozenset[str] = frozenset()
    trace_scopes: frozenset[str] = frozenset()


_lock = RLock()
_config = _ObservabilityConfig()
_UNSET = object()


def configure_observability(
    *,
    debug_sink: DebugLogSinkProtocol | None | object = _UNSET,
    trace_sink: TraceSinkProtocol | None | object = _UNSET,
    problem_sink: InMemoryProblemStore | None | object = _UNSET,
    debug_scopes: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None | object = _UNSET,
    trace_scopes: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None | object = _UNSET,
) -> None:
    with _lock:
        if problem_sink is None:
            _config.problem_store = InMemoryProblemStore()
        elif problem_sink is not _UNSET:
            _config.problem_store = problem_sink
        if debug_sink is not _UNSET:
            _config.debug_sink = debug_sink
            if debug_sink is None and debug_scopes is _UNSET:
                _config.debug_scopes = frozenset()
        if trace_sink is not _UNSET:
            _config.trace_sink = trace_sink
            if trace_sink is None and trace_scopes is _UNSET:
                _config.trace_scopes = frozenset()
        if debug_scopes is not _UNSET:
            _config.debug_scopes = _normalize_scopes(debug_scopes)
        if trace_scopes is not _UNSET:
            _config.trace_scopes = _normalize_scopes(trace_scopes)


def capture_observability() -> _ObservabilityConfig:
    with _lock:
        return _ObservabilityConfig(
            problem_store=_config.problem_store,
            debug_sink=_config.debug_sink,
            trace_sink=_config.trace_sink,
            debug_scopes=_config.debug_scopes,
            trace_scopes=_config.trace_scopes,
        )


def restore_observability(snapshot: _ObservabilityConfig) -> None:
    with _lock:
        _config.problem_store = snapshot.problem_store
        _config.debug_sink = snapshot.debug_sink
        _config.trace_sink = snapshot.trace_sink
        _config.debug_scopes = snapshot.debug_scopes
        _config.trace_scopes = snapshot.trace_scopes


def configure_debug_logging(
    *,
    debug_sink: DebugLogSinkProtocol | None,
    debug_scopes: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
) -> None:
    with _lock:
        _config.debug_sink = debug_sink
        _config.debug_scopes = _normalize_scopes(debug_scopes)


def reset_observability() -> None:
    global _config
    with _lock:
        _config = _ObservabilityConfig()


def get_problem_store() -> InMemoryProblemStore:
    with _lock:
        return _config.problem_store


def emit_log(
    *,
    level: str,
    module: str,
    component: str | None,
    message: str,
    details: dict[str, JSONValue],
) -> None:
    with _lock:
        sink = _config.debug_sink
    if sink is None:
        return
    _best_effort(
        sink.write_log,
        level=level,
        module=module,
        component=component,
        message=message,
        context=current_context(),
        details=details,
    )


def emit_problem(record: ProblemRecord) -> None:
    with _lock:
        problem_store = _config.problem_store
        debug_sink = _config.debug_sink
        trace_sink = _config.trace_sink
        trace_scopes = _config.trace_scopes

    _best_effort(problem_store.record_problem, record)
    if debug_sink is not None:
        _best_effort(debug_sink.write_problem, record)
    if trace_sink is not None and _scope_matches(trace_scopes, "problem"):
        _best_effort(trace_sink.write_problem, record)


def emit_debug_event(record: DebugEventRecord) -> None:
    with _lock:
        debug_sink = _config.debug_sink
        trace_sink = _config.trace_sink
        debug_scopes = _config.debug_scopes
        trace_scopes = _config.trace_scopes

    if debug_sink is not None and _scope_matches(debug_scopes, record.scope):
        _best_effort(debug_sink.write_debug_event, record)
    if trace_sink is not None and _scope_matches(trace_scopes, record.scope):
        _best_effort(trace_sink.write_debug_event, record)


def is_debug_event_enabled(scope: str) -> bool:
    with _lock:
        debug_sink = _config.debug_sink
        trace_sink = _config.trace_sink
        debug_scopes = _config.debug_scopes
        trace_scopes = _config.trace_scopes

    return (
        (debug_sink is not None and _scope_matches(debug_scopes, scope))
        or (trace_sink is not None and _scope_matches(trace_scopes, scope))
    )


def _normalize_scopes(
    scopes: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None,
) -> frozenset[str]:
    if scopes is None:
        return frozenset()
    return frozenset(scope.strip() for scope in scopes if scope.strip())


def _scope_matches(scopes: frozenset[str], scope: str) -> bool:
    return "all" in scopes or scope in scopes


def _best_effort(callback: Callable[..., None], *args: object, **kwargs: object) -> None:
    try:
        callback(*args, **kwargs)
    except Exception:  # noqa: BLE001
        return
