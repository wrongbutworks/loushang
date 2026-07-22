"""Shared CLI-to-session resolution over the Harness lifecycle capability."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loushang.harness.session import require_session_operation_session


@dataclass(frozen=True, slots=True)
class SessionResolutionRequest:
    session: str | None = None
    continue_: bool = False
    resume: bool | str = False
    fork: str | None = None
    cwd: str | Path = "."


async def resolve_session(runtime: object, request: SessionResolutionRequest) -> object:
    """Resolve a new, resumed, continued, or forked session."""

    if isinstance(request.resume, str):
        session = require_session_operation_session(
            await runtime.restore_session_operation(request.resume)
        )
    elif request.continue_ or request.resume:
        latest_session_file = resolve_latest_session_file(runtime)
        if latest_session_file is None:
            raise RuntimeError(
                "No existing session found. Use --session or --resume <session> "
                "to restore a specific session."
            )
        session = require_session_operation_session(
            await runtime.restore_session_operation(latest_session_file)
        )
    elif request.session:
        session = require_session_operation_session(
            await runtime.restore_session_operation(request.session)
        )
    else:
        session = require_session_operation_session(
            await runtime.new_session_operation(cwd=str(request.cwd))
        )

    if request.fork:
        try:
            session = require_session_operation_session(
                await runtime.fork_session_operation(request.fork, position="at")
            )
        except Exception as error:
            raise RuntimeError(f"Failed to fork session: {error}") from error
    return session


def resolve_latest_session_file(runtime: object) -> str | None:
    try:
        sessions = runtime.list_sessions()
    except Exception as error:
        raise RuntimeError(f"Failed to list sessions: {error}") from error
    if not isinstance(sessions, list):
        raise RuntimeError("session listing returned an invalid response.")
    if not sessions:
        return None
    for latest_session in sessions:
        session_file = getattr(latest_session, "session_file", None)
        if session_file is not None:
            return str(session_file)
    return None


__all__ = [
    "SessionResolutionRequest",
    "resolve_latest_session_file",
    "resolve_session",
]
