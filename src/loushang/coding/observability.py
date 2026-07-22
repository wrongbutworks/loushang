"""Coding observability binding over the shared Harness runtime."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loushang.harness.diagnostics.observability_bridge import (
    diagnostic_source_for_problem,
)
from loushang.harness.diagnostics.observability_runtime import (
    disable_session_debug,
    session_observability_context,
    startup_observability_context,
)
from loushang.harness.diagnostics.observability_runtime import (
    enable_session_debug as _enable_session_debug,
)
from loushang.observability import ProblemRecord, session_log_label


@contextmanager
def coding_observability_context(
    *,
    args: Any,
    session: Any,
    cwd: str | Path,
    mode: str,
) -> Iterator[None]:
    with session_observability_context(
        args=args,
        session=session,
        cwd=cwd,
        mode=mode,
        source_resolver=_coding_diagnostic_source,
        debug_dir=_default_debug_dir(),
        trace_dir=_default_trace_dir(),
        session_label=_safe_session_label(_session_id(session)),
    ):
        yield


@contextmanager
def coding_startup_observability_context(
    *,
    args: Any,
    services: Any,
    cwd: str | Path,
) -> Iterator[None]:
    with startup_observability_context(
        args=args,
        services=services,
        cwd=cwd,
        source_resolver=_coding_diagnostic_source,
        debug_dir=_default_debug_dir(),
        trace_dir=_default_trace_dir(),
        session_label=_safe_session_label(None),
    ):
        yield


def enable_session_debug(
    *,
    session: Any,
    scopes: tuple[str, ...] = ("all",),
    debug_file: str | Path | None = None,
) -> Path:
    return _enable_session_debug(
        session=session,
        scopes=scopes,
        debug_file=debug_file,
    )


def _coding_diagnostic_source(record: ProblemRecord):
    if record.source == "config":
        return "model"
    return diagnostic_source_for_problem(record)


def _session_id(session: Any) -> str | None:
    try:
        value = getattr(session, "session_id", None)
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def _safe_session_label(session_id: str | None) -> str:
    return session_log_label(session_id, now=time.time())


def _default_debug_dir() -> Path:
    return Path.home() / ".loushang" / "debug"


def _default_trace_dir() -> Path:
    return Path.home() / ".loushang" / "traces"


__all__ = [
    "coding_observability_context",
    "coding_startup_observability_context",
    "disable_session_debug",
    "enable_session_debug",
]
