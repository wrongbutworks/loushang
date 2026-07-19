from __future__ import annotations

from loushang.harnesstui.conversation.startup import (
    build_conversation_startup_view,
)


def test_build_conversation_startup_view_derives_project_label() -> None:
    view = build_conversation_startup_view(
        model_label="provider/model",
        cwd="/workspace/project",
        branch="main",
        session_label="session",
        session_observability_id="session-id",
    )

    assert view.model_label == "provider/model"
    assert view.cwd == "/workspace/project"
    assert view.branch == "main"
    assert view.project_label == "project"
    assert view.session_label == "session"
    assert view.session_observability_id == "session-id"


def test_build_conversation_startup_view_preserves_root_as_project_label() -> None:
    view = build_conversation_startup_view(
        model_label=None,
        cwd="/",
        branch=None,
        session_label=None,
        session_observability_id=None,
    )

    assert view.project_label == "/"
