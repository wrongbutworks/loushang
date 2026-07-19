from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from loushang.coding.presentation.resume import coding_resume_hint_for_session


def test_coding_resume_hint_prefers_session_id() -> None:
    session = SimpleNamespace(
        session_id="session-id",
        session_manager=SimpleNamespace(
            get_session_file=lambda: Path("/tmp/session.jsonl"),
            get_header=lambda: SimpleNamespace(conversation_id="header-id"),
        ),
    )

    hint = coding_resume_hint_for_session(session)

    assert hint is not None
    assert hint.heading == "Resume this session with:"
    assert hint.command == ("loushang", "--resume", "session-id")


def test_coding_resume_hint_falls_back_to_header_then_file() -> None:
    session_file = Path("/tmp/a session.jsonl")
    manager = SimpleNamespace(
        get_session_file=lambda: session_file,
        get_header=lambda: SimpleNamespace(conversation_id="header-id"),
    )

    header_hint = coding_resume_hint_for_session(
        SimpleNamespace(session_id=None, session_manager=manager)
    )
    file_hint = coding_resume_hint_for_session(
        SimpleNamespace(
            session_id=None,
            session_manager=SimpleNamespace(
                get_session_file=lambda: session_file,
                get_header=lambda: None,
            ),
        )
    )

    assert header_hint is not None
    assert header_hint.command[-1] == "header-id"
    assert file_hint is not None
    assert file_hint.command[-1] == str(session_file)


def test_coding_resume_hint_requires_a_session_file() -> None:
    session = SimpleNamespace(
        session_id="session-id",
        session_manager=SimpleNamespace(get_session_file=lambda: None),
    )

    assert coding_resume_hint_for_session(session) is None
