from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from loushang.coding.diagnostics.problem_bridge import DiagnosticsProblemStore
from loushang.observability import (
    DebugLogSink,
    TraceJSONLSink,
    capture_observability,
    configure_debug_logging,
    configure_observability,
    log_context,
    restore_observability,
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
    debug_raw = _scope_value(args, "debug", "LOUSHANG_DEBUG_SCOPES")
    trace_raw = _scope_value(args, "trace", "LOUSHANG_TRACE_SCOPES")
    debug_scopes = _parse_scopes(debug_raw, bare_default=("all",))
    trace_scopes = _parse_scopes(trace_raw, bare_default=("all",))
    debug_path = _debug_path(args=args, session_label=session_label, debug_raw=debug_raw)
    trace_path = _trace_path(args=args, session_label=session_label, trace_raw=trace_raw)
    problem_sink = _problem_sink(session)

    configure_kwargs: dict[str, object] = {}
    if debug_path is not None:
        configure_kwargs["debug_sink"] = DebugLogSink(debug_path, latest_path=debug_path.parent / "latest")
        configure_kwargs["debug_scopes"] = debug_scopes
    if trace_path is not None:
        configure_kwargs["trace_sink"] = TraceJSONLSink(trace_path, latest_path=trace_path.parent / "latest")
        configure_kwargs["trace_scopes"] = trace_scopes
    if problem_sink is not None:
        configure_kwargs["problem_sink"] = problem_sink

    previous_observability = None
    if configure_kwargs:
        previous_observability = capture_observability()
        configure_observability(**configure_kwargs)

    try:
        with log_context(session_id=session_id, cwd=str(cwd_path), mode=mode):
            yield
    finally:
        if previous_observability is not None:
            restore_observability(previous_observability)


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
    configure_debug_logging(
        debug_sink=DebugLogSink(debug_path, latest_path=debug_path.parent / "latest"),
        debug_scopes=scopes,
    )
    return debug_path


def disable_session_debug() -> None:
    configure_debug_logging(debug_sink=None)


def _parse_scopes(raw: str | None, *, bare_default: tuple[str, ...]) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if raw == "":
        return frozenset(bare_default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _scope_value(args: Any, arg_name: str, env_name: str) -> str | None:
    value = getattr(args, arg_name, None)
    if value is not None:
        return value
    return os.environ.get(env_name)


def _path_value(args: Any, arg_name: str, env_name: str) -> str | None:
    value = getattr(args, arg_name, None)
    if value:
        return value
    return os.environ.get(env_name)


def _debug_path(*, args: Any, session_label: str, debug_raw: str | None) -> Path | None:
    explicit = _path_value(args, "debug_file", "LOUSHANG_DEBUG_FILE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if debug_raw is None:
        return None
    return _default_debug_dir() / f"{session_label}.log"


def _trace_path(*, args: Any, session_label: str, trace_raw: str | None) -> Path | None:
    explicit = _path_value(args, "trace_file", "LOUSHANG_TRACE_FILE")
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
    if diagnostics_service is None or not callable(getattr(diagnostics_service, "record", None)):
        return None
    return DiagnosticsProblemStore(diagnostics_service)


def _safe_session_label(session_id: str | None) -> str:
    raw = session_id or f"startup-{int(time.time() * 1000)}-{os.getpid()}"
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in raw)


def _default_debug_dir() -> Path:
    return Path.home() / ".loushang" / "debug"


def _default_trace_dir() -> Path:
    return Path.home() / ".loushang" / "traces"
