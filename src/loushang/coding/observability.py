from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from loushang.harness.diagnostics.observability_bridge import (
    DiagnosticsProblemStore,
    diagnostic_source_for_problem,
)
from loushang.harness.diagnostics.types import DiagnosticSource
from loushang.observability import (
    ProblemRecord,
    disable_debug_file,
    enable_debug_file,
    observability_runtime_context,
    parse_scopes,
    path_from_args_or_env,
    session_log_label,
    value_from_args_or_env,
)


@contextmanager
def coding_observability_context(
    *,
    args: Any,
    session: Any,
    cwd: str | Path,
    mode: str,
) -> Iterator[None]:
    cwd_path = Path(cwd).expanduser().resolve()
    session_id = _session_id(session)
    session_label = _safe_session_label(session_id)
    debug_raw = value_from_args_or_env(args, "debug", "LOUSHANG_DEBUG_SCOPES")
    trace_raw = value_from_args_or_env(args, "trace", "LOUSHANG_TRACE_SCOPES")
    debug_scopes = parse_scopes(debug_raw, bare_default=("all",))
    trace_scopes = parse_scopes(trace_raw, bare_default=("all",))
    debug_path = _debug_path(
        args=args, session_label=session_label, debug_raw=debug_raw
    )
    trace_path = _trace_path(
        args=args, session_label=session_label, trace_raw=trace_raw
    )
    problem_sink = _problem_sink(session)

    with observability_runtime_context(
        session_id=session_id,
        cwd=cwd_path,
        mode=mode,
        debug_path=debug_path,
        debug_scopes=debug_scopes,
        trace_path=trace_path,
        trace_scopes=trace_scopes,
        problem_sink=problem_sink,
    ):
        yield


@contextmanager
def coding_startup_observability_context(
    *,
    args: Any,
    services: Any,
    cwd: str | Path,
) -> Iterator[None]:
    startup_session = SimpleNamespace(
        session_id=None,
        diagnostics_service=getattr(services, "diagnostics_service", None),
    )
    with coding_observability_context(
        args=args,
        session=startup_session,
        cwd=cwd,
        mode="startup",
    ):
        yield


def enable_session_debug(
    *,
    session: Any,
    scopes: tuple[str, ...] = ("all",),
    debug_file: str | Path | None = None,
) -> Path:
    session_id = _session_id(session)
    debug_path = (
        Path(debug_file).expanduser().resolve()
        if debug_file is not None
        else _default_debug_dir() / f"{_safe_session_label(session_id)}.log"
    )
    return enable_debug_file(debug_path, scopes=scopes)


def disable_session_debug() -> None:
    disable_debug_file()


def _debug_path(*, args: Any, session_label: str, debug_raw: str | None) -> Path | None:
    explicit = path_from_args_or_env(args, "debug_file", "LOUSHANG_DEBUG_FILE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if debug_raw is None:
        return None
    return _default_debug_dir() / f"{session_label}.log"


def _trace_path(*, args: Any, session_label: str, trace_raw: str | None) -> Path | None:
    explicit = path_from_args_or_env(args, "trace_file", "LOUSHANG_TRACE_FILE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if trace_raw is None:
        return None
    return _default_trace_dir() / f"{session_label}.jsonl"


def _session_id(session: Any) -> str | None:
    try:
        value = getattr(session, "session_id", None)
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def _problem_sink(session: Any):
    diagnostics_service = getattr(session, "diagnostics_service", None)
    if diagnostics_service is None or not callable(
        getattr(diagnostics_service, "record", None)
    ):
        return None
    return DiagnosticsProblemStore(
        diagnostics_service,
        source_resolver=_coding_diagnostic_source,
    )


def _coding_diagnostic_source(record: ProblemRecord) -> DiagnosticSource:
    """Apply Coding's model-configuration diagnostic classification."""

    if record.source == "config":
        return "model"
    return diagnostic_source_for_problem(record)


def _safe_session_label(session_id: str | None) -> str:
    return session_log_label(session_id, now=time.time())


def _default_debug_dir() -> Path:
    return Path.home() / ".loushang" / "debug"


def _default_trace_dir() -> Path:
    return Path.home() / ".loushang" / "traces"
