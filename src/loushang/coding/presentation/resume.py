from __future__ import annotations

from typing import Any

from loushang.harnesstui.conversation.resume import ConversationResumeHint


def coding_resume_hint_for_session(session: Any) -> ConversationResumeHint | None:
    """Prepare Coding copy and command arguments from Coding session policy."""

    resume_ref = _resume_ref_for_session(session)
    if resume_ref is None:
        return None
    return ConversationResumeHint(
        heading="Resume this session with:",
        command=("loushang", "--resume", resume_ref),
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


__all__ = ["coding_resume_hint_for_session"]
