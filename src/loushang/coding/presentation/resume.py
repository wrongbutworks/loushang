from __future__ import annotations

import shlex
from typing import Any, TextIO


def write_resume_hint_for_clean_exit(
    *,
    session: Any,
    stdout: TextIO,
    exit_code: int,
) -> None:
    if exit_code != 0:
        return
    command = resume_command_for_session(session)
    if command is None:
        return
    stdout.write(f"\nResume this session with:\n{command}\n")
    stdout.flush()


def resume_command_for_session(session: Any) -> str | None:
    resume_ref = _resume_ref_for_session(session)
    if resume_ref is None:
        return None
    return " ".join(
        shlex.quote(part) for part in ("loushang", "--resume", resume_ref)
    )


def _resume_ref_for_session(session: Any) -> str | None:
    session_file = _session_file_for_resume(session)
    if session_file is None:
        return None

    session_id = getattr(session, "session_id", None)
    if isinstance(session_id, str) and session_id:
        return session_id

    manager = getattr(session, "session_manager", None)
    get_header = getattr(manager, "get_header", None)
    if callable(get_header):
        try:
            header = get_header()
        except Exception:
            header = None
        header_id = getattr(header, "conversation_id", None)
        if isinstance(header_id, str) and header_id:
            return header_id

    return str(session_file)


def _session_file_for_resume(session: Any) -> object | None:
    manager = getattr(session, "session_manager", None)
    get_session_file = getattr(manager, "get_session_file", None)
    if callable(get_session_file):
        try:
            return get_session_file()
        except Exception:
            return None
    return getattr(session, "session_file", None)


__all__ = ["resume_command_for_session", "write_resume_hint_for_clean_exit"]
