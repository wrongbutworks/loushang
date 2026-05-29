from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from loushang.ai.model import Capabilities, Model
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage


def _runtime_footer(cwd: Path) -> str:
    return f"Current date: {date.today().isoformat()}\nCurrent working directory: {cwd.as_posix()}"


def _model() -> Model:
    return Model(
        id="faux-model",
        name="Faux",
        provider="faux",
        endpoint="anthropic-messages",
        capabilities=Capabilities(
            reasoning=True,
            input=("text",),
            context_window=128000,
            max_tokens=4096,
        ),
    )


def _usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost={},
    )


def _user_message(text: str) -> UserMessage:
    return UserMessage(
        role="user",
        content=[TextPart(type="text", text=text)],
        timestamp=0.0,
    )


def _assistant_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=_usage(),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


def test_runtime_create_switch_and_list_sessions(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()

    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)

    first = asyncio.run(runtime.create_session(cwd=str(project_a)))
    first.session_manager.append_message(_user_message("first"))

    second_manager = SessionManager.new(session_dir=tmp_path, cwd=str(project_b.resolve()), persist=True)
    second_manager.append_message(_user_message("second"))
    assert second_manager.session_file is not None

    switched = asyncio.run(runtime.switch_session(second_manager.session_file))
    records = runtime.list_sessions()

    assert runtime.get_current_session() is switched
    assert [message.content[0].text for message in switched.get_session_context().messages] == ["second"]
    assert [record.cwd for record in records] == [str(project_b.resolve()), str(project_a.resolve())]


def test_runtime_clone_session_forks_current_leaf(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    session.session_manager.append_message(_user_message("first"))
    session.session_manager.append_message(_assistant_message("second"))
    leaf_id = session.session_manager.get_leaf_id()

    cloned = asyncio.run(runtime.clone_session())

    assert runtime.get_current_session() is cloned
    assert cloned.session_manager.session_file != session.session_manager.session_file
    assert cloned.session_manager.get_leaf_id() == leaf_id
    assert [message.content[0].text for message in cloned.get_session_context().messages] == ["first", "second"]


def test_runtime_lists_session_summaries(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    session.set_session_name("Runtime Summary")
    asyncio.run(session.set_model(_model()))
    session.session_manager.append_message(_user_message("summarize runtime sessions"))

    summaries = runtime.list_session_summaries()

    assert len(summaries) == 1
    assert summaries[0].session_id == session.session_id
    assert summaries[0].name == "Runtime Summary"
    assert summaries[0].last_message_preview == "summarize runtime sessions"
    assert summaries[0].model == {"provider": "faux", "model_id": "faux-model"}


def test_runtime_finds_session_summaries(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionQuery

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)

    first = asyncio.run(runtime.create_session(cwd=str(project_a)))
    first.set_session_name("Alpha")
    first.session_manager.append_message(_user_message("alpha repository task"))

    second = asyncio.run(runtime.create_session(cwd=str(project_b), parent_session=str(first.session_file)))
    second.set_session_name("Beta")
    second.session_manager.append_message(_user_message("beta follow up"))

    summaries = runtime.find_session_summaries(SessionQuery(name="bet", text="follow", limit=1))

    assert [summary.session_id for summary in summaries] == [second.session_id]


def test_runtime_renames_and_deletes_sessions_by_resolved_reference(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    current = asyncio.run(runtime.create_session(cwd=str(project)))

    other_manager = SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True)
    other_file = other_manager.get_session_file()
    assert other_file is not None

    renamed = runtime.rename_session(other_manager.get_header().id[:4], "Other Session")
    deleted = runtime.delete_session(other_manager.get_header().id[:4])

    assert renamed.name == "Other Session"
    assert deleted is True
    assert other_file.exists() is False
    assert current.session_manager.get_session_file() is not None
    assert current.session_manager.get_session_file().exists() is True


def test_runtime_delete_session_refuses_current_session(tmp_path) -> None:
    import pytest

    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    current = asyncio.run(runtime.create_session(cwd=str(project)))
    session_file = current.session_manager.get_session_file()
    assert session_file is not None

    with pytest.raises(ValueError, match="currently active session"):
        runtime.delete_session(session_file)

    assert session_file.exists() is True


def test_runtime_rename_session_records_failure_diagnostic(tmp_path) -> None:
    import pytest

    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.session_id = manager.get_header().id

    project = tmp_path / "project"
    project.mkdir()
    diagnostics_service = DiagnosticsService()
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=DummySession,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    current = asyncio.run(runtime.create_session(cwd=str(project)))

    with pytest.raises(FileNotFoundError):
        runtime.rename_session("missing-session", "New Name")

    records = diagnostics_service.get_diagnostics(query=DiagnosticsQuery(code="session_rename_failed"))

    assert runtime.get_current_session() is current
    assert len(records) == 1
    assert records[0].session_id == current.session_id
    assert records[0].details == {
        "operation": "rename_session",
        "session_ref": "missing-session",
        "target_session_file": None,
        "name": "New Name",
    }


def test_runtime_delete_session_records_failure_diagnostic(tmp_path) -> None:
    import pytest

    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.session_id = manager.get_header().id

    project = tmp_path / "project"
    project.mkdir()
    diagnostics_service = DiagnosticsService()
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=DummySession,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    current = asyncio.run(runtime.create_session(cwd=str(project)))

    with pytest.raises(FileNotFoundError):
        runtime.delete_session("missing-session")

    records = diagnostics_service.get_diagnostics(query=DiagnosticsQuery(code="session_delete_failed"))

    assert runtime.get_current_session() is current
    assert len(records) == 1
    assert records[0].session_id == current.session_id
    assert records[0].details == {
        "operation": "delete_session",
        "session_ref": "missing-session",
        "target_session_file": None,
    }


def test_runtime_lists_all_session_summaries_across_session_dirs(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    sessions_root = tmp_path / "sessions"
    runtime_a = create_agent_session_runtime(session_dir=sessions_root / "project-a", model=_model(), persist=True)
    runtime_b = create_agent_session_runtime(session_dir=sessions_root / "project-b", model=_model(), persist=True)

    first = asyncio.run(runtime_a.create_session(cwd=str(project_a)))
    first.set_session_name("Alpha")
    second = asyncio.run(runtime_b.create_session(cwd=str(project_b)))
    second.set_session_name("Beta")

    summaries = runtime_a.list_all_session_summaries()

    assert {summary.session_id for summary in summaries} == {first.session_id, second.session_id}
    assert {summary.name for summary in summaries} == {"Alpha", "Beta"}


def test_runtime_finds_all_session_summaries_across_session_dirs(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionQuery

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    sessions_root = tmp_path / "sessions"
    runtime_a = create_agent_session_runtime(session_dir=sessions_root / "project-a", model=_model(), persist=True)
    runtime_b = create_agent_session_runtime(session_dir=sessions_root / "project-b", model=_model(), persist=True)

    asyncio.run(runtime_a.create_session(cwd=str(project_a))).set_session_name("Alpha")
    second = asyncio.run(runtime_b.create_session(cwd=str(project_b)))
    second.set_session_name("Beta")
    second.session_manager.append_message(_user_message("global lookup target"))

    summaries = runtime_a.find_all_session_summaries(SessionQuery(text="lookup target"))

    assert [summary.session_id for summary in summaries] == [second.session_id]


def test_runtime_exposes_indexed_session_summary_facades(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionQuery

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    project_a.mkdir()
    project_b.mkdir()
    sessions_root = tmp_path / "sessions"
    runtime_a = create_agent_session_runtime(session_dir=sessions_root / "project-a", model=_model(), persist=True)
    runtime_b = create_agent_session_runtime(session_dir=sessions_root / "project-b", model=_model(), persist=True)

    first = asyncio.run(runtime_a.create_session(cwd=str(project_a)))
    first.session_manager.append_message(_user_message("indexed alpha"))
    second = asyncio.run(runtime_b.create_session(cwd=str(project_b)))
    second.session_manager.append_message(_user_message("indexed beta"))

    assert [summary.session_id for summary in runtime_a.refresh_session_index()] == [first.session_id]
    assert [summary.session_id for summary in runtime_a.list_indexed_session_summaries()] == [first.session_id]
    assert [summary.session_id for summary in runtime_a.find_indexed_session_summaries(SessionQuery(text="alpha"))] == [
        first.session_id
    ]
    assert [summary.session_id for summary in runtime_a.refresh_all_session_indexes()] == [second.session_id, first.session_id]
    assert [summary.session_id for summary in runtime_a.find_all_indexed_session_summaries(SessionQuery(text="beta"))] == [
        second.session_id
    ]


def test_runtime_auto_refreshes_session_index_after_replacement(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    runtime.auto_refresh_session_index = True
    runtime.session_index_flush_delay = 0.01

    async def scenario():
        session = await runtime.create_session(cwd=str(project))
        assert not SessionManager.index_file(tmp_path).exists()
        await asyncio.sleep(0.02)
        return session

    session = asyncio.run(scenario())

    assert SessionManager.index_file(tmp_path).exists()
    assert [summary.session_id for summary in runtime.list_indexed_session_summaries()] == [session.session_id]


def test_runtime_auto_refreshes_session_index_after_rename_and_delete(tmp_path) -> None:
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager),
        persist=True,
        auto_refresh_session_index=True,
        session_index_flush_delay=60.0,
    )
    project = tmp_path / "project"
    project.mkdir()
    first = SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True)
    second = SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True)

    async def scenario() -> None:
        runtime.rename_session(first.get_header().id, "Renamed")
        assert SessionManager.load_index(tmp_path) == []
        await runtime.drain_session_index_flush()
        assert next(
            summary
            for summary in SessionManager.load_index(tmp_path)
            if summary.session_id == first.get_header().id
        ).name == "Renamed"

        runtime.delete_session(second.get_header().id)
        await runtime.drain_session_index_flush()

    asyncio.run(scenario())

    assert {summary.session_id for summary in SessionManager.load_index(tmp_path)} == {first.get_header().id}


def test_runtime_auto_index_refresh_uses_debounce_interval(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    runtime.auto_refresh_session_index = True
    runtime.session_index_refresh_interval = 60.0

    async def scenario():
        session = await runtime.create_session(cwd=str(project))
        await runtime.drain_session_index_flush()
        return session

    session = asyncio.run(scenario())
    index_file = SessionManager.index_file(tmp_path)
    first_mtime = index_file.stat().st_mtime_ns

    session.session_manager.append_message(_user_message("not refreshed yet"))
    summaries = runtime.list_indexed_session_summaries()

    assert index_file.stat().st_mtime_ns == first_mtime
    assert [summary.session_id for summary in summaries] == [session.session_id]
    assert "not refreshed yet" not in summaries[0].all_messages_text


def test_runtime_list_sessions_ignores_default_jsonl_exports(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project_root)))
    session.session_manager.append_message(_user_message("first"))

    export_path = session.export_to_jsonl()
    records = runtime.list_sessions()

    assert Path(export_path).name.startswith("session-")
    assert Path(export_path).parent == project_root
    assert [record.session_id for record in records] == [session.session_id]
    assert records[0].session_file != export_path


def test_runtime_list_sessions_skips_invalid_session_files(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    session.session_manager.append_message(_user_message("hello"))

    (tmp_path / "broken.jsonl").write_text("not json\n", encoding="utf-8")
    (tmp_path / "not-session.jsonl").write_text("{}\n", encoding="utf-8")

    records = runtime.list_sessions()

    assert [record.session_id for record in records] == [session.session_id]


def test_runtime_fork_session_switches_to_selected_branch(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    nested = project_root / "app"
    nested.mkdir(parents=True)
    (project_root / "AGENTS.md").write_text("Keep edits minimal.", encoding="utf-8")

    runtime = create_agent_session_runtime(
        session_dir=tmp_path,
        model=_model(),
        system_prompt="Base instructions.",
        persist=True,
    )
    session = asyncio.run(runtime.create_session(cwd=str(nested)))

    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    session.session_manager.append_message(_user_message("tail"))
    original_file = session.session_manager.session_file

    forked = asyncio.run(runtime.fork_session(second_id))

    assert runtime.get_current_session() is forked
    assert original_file is not None
    assert forked.session_manager.session_file is not None
    assert forked.session_manager.session_file != original_file
    assert forked.session_manager.get_header().parent_session == str(original_file)
    assert [entry.id for entry in forked.session_manager.get_branch()] == [first_id, second_id]
    assert [message.content[0].text for message in forked.get_session_context().messages] == ["root", "answer"]
    expected_context = (
        "# Project Context\n\n"
        "Project-specific instructions and guidelines:\n\n"
        f"## {project_root / 'AGENTS.md'}\n\n"
        "Keep edits minimal."
    )
    assert forked.agent.system_prompt == (
        f"Base instructions.\n\n{expected_context}\n\n{_runtime_footer(nested)}"
    )


def test_runtime_fork_session_before_user_message_returns_selected_text(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project_root)))
    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    third_id = session.session_manager.append_message(_user_message("tail"))

    forked, selected_text = asyncio.run(runtime.fork_session_with_result(third_id, position="before"))

    assert runtime.get_current_session() is forked
    assert selected_text == "tail"
    assert [entry.id for entry in forked.session_manager.get_branch()] == [first_id, second_id]


def test_runtime_fork_before_requires_user_message(tmp_path) -> None:
    import pytest

    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project_root)))
    session.session_manager.append_message(_user_message("root"))
    assistant_id = session.session_manager.append_message(_assistant_message("answer"))

    with pytest.raises(ValueError, match="requires a user message entry"):
        asyncio.run(runtime.fork_session_with_result(assistant_id, position="before"))


def test_runtime_exposes_pi_style_lifecycle_method_aliases(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project_root)))
    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    third_id = session.session_manager.append_message(_user_message("tail"))
    first_session_file = session.session_manager.session_file
    assert first_session_file is not None

    fork_result = asyncio.run(runtime.fork(third_id))
    forked = runtime.get_current_session()
    assert fork_result == {"cancelled": False, "selectedText": "tail", "selected_text": "tail"}
    assert forked is not None
    assert [entry.id for entry in forked.session_manager.get_branch()] == [first_id, second_id]

    switch_result = asyncio.run(runtime.switchSession(first_session_file))
    assert switch_result == {"cancelled": False}
    assert runtime.get_current_session() is not forked

    new_result = asyncio.run(runtime.newSession({"parentSession": str(first_session_file)}))
    assert new_result == {"cancelled": False}
    assert runtime.get_current_session().session_manager.get_header().parent_session == str(first_session_file)


def test_runtime_pi_style_new_session_runs_setup_and_with_session(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project_root)))
    first_session_file = session.session_manager.session_file
    assert first_session_file is not None
    events: list[tuple[str, object]] = []

    async def _setup(manager):
        events.append(("setup", manager.get_cwd()))
        manager.append_message(_user_message("initialized from setup"))

    async def _with_session(ctx):
        events.append(("withSession", (ctx.cwd, ctx.sessionManager is runtime.get_current_session().session_manager)))

    result = asyncio.run(runtime.newSession(
        {
            "parentSession": str(first_session_file),
            "setup": _setup,
            "withSession": _with_session,
        }
    ))
    created = runtime.get_current_session()

    assert result == {"cancelled": False}
    assert created is not None
    assert created is not session
    assert created.session_manager.get_header().parent_session == str(first_session_file)
    assert [message.content[0].text for message in created.get_session_context().messages] == ["initialized from setup"]
    assert [message.content[0].text for message in created.agent.state.messages] == ["initialized from setup"]
    assert events == [
        ("setup", str(project_root.resolve())),
        ("withSession", (str(project_root.resolve()), True)),
    ]


def test_runtime_pi_style_switch_and_fork_run_with_session(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    session = asyncio.run(runtime.create_session(cwd=str(project_root)))
    user_id = session.session_manager.append_message(_user_message("root"))
    session.session_manager.append_message(_assistant_message("answer"))

    target_manager = SessionManager.new(session_dir=tmp_path, cwd=str(project_root), persist=True)
    target_manager.append_message(_user_message("target"))
    target_file = target_manager.session_file
    assert target_file is not None

    events: list[tuple[str, object]] = []

    async def _switch_with_session(ctx):
        events.append(("switch", [message.content[0].text for message in ctx.sessionManager.build_session_context().messages]))

    async def _fork_with_session(ctx):
        events.append(("fork", [entry.id for entry in ctx.sessionManager.get_branch()]))

    switch_result = asyncio.run(runtime.switchSession(target_file, {"withSession": _switch_with_session}))
    switch_session = runtime.get_current_session()
    assert switch_session is not None

    asyncio.run(runtime.switchSession(session.session_manager.session_file))
    fork_result = asyncio.run(runtime.fork(user_id, {"position": "at", "withSession": _fork_with_session}))

    assert switch_result == {"cancelled": False}
    assert fork_result == {"cancelled": False}
    assert events == [
        ("switch", ["target"]),
        ("fork", [user_id]),
    ]


def test_runtime_replacement_callbacks_require_async_callables(tmp_path) -> None:
    import pytest

    from loushang.coding.bootstrap import create_agent_session_runtime

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    asyncio.run(runtime.create_session(cwd=str(project_root)))

    def _sync_setup(manager):
        del manager

    with pytest.raises(TypeError, match="setup callback must be an async callable"):
        asyncio.run(runtime.newSession({"setup": _sync_setup}))


def test_runtime_replacement_callback_failures_keep_replacement_and_record_diagnostics(tmp_path) -> None:
    import pytest

    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.session_id = manager.get_header().id
            self.extension_runner = None
            self.diagnostics_service = diagnostics_service
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    diagnostics_service = DiagnosticsService()
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=DummySession,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    project_root = tmp_path / "project"
    target_root = tmp_path / "target"
    project_root.mkdir()
    target_root.mkdir()
    target_manager = SessionManager.new(session_dir=tmp_path, cwd=str(target_root), persist=True)
    target_file = target_manager.session_file
    assert target_file is not None

    async def _setup(manager: SessionManager) -> None:
        assert manager.get_cwd() == str(project_root.resolve())
        raise RuntimeError("setup boom")

    with pytest.raises(RuntimeError, match="setup boom"):
        asyncio.run(runtime.newSession({"cwd": str(project_root), "setup": _setup}))

    setup_session = runtime.get_current_session()
    assert setup_session is not None
    assert setup_session.session_manager.get_cwd() == str(project_root.resolve())

    async def _with_session(ctx) -> None:
        assert ctx.cwd == str(target_root.resolve())
        raise RuntimeError("withSession boom")

    with pytest.raises(RuntimeError, match="withSession boom"):
        asyncio.run(runtime.switchSession(target_file, {"withSession": _with_session}))

    current = runtime.get_current_session()
    records = diagnostics_service.get_diagnostics(
        query=DiagnosticsQuery(code="session_replacement_callback_failed")
    )

    assert current is not None
    assert current.session_manager.session_file == target_file
    assert [(record.message, record.details["callback"]) for record in records] == [
        ("setup boom", "setup"),
        ("withSession boom", "withSession"),
    ]
    assert records[0].session_id == setup_session.session_id
    assert records[1].session_id == current.session_id


def test_runtime_import_from_jsonl_copies_and_switches_session(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    project_root.mkdir()
    import_dir = tmp_path / "imports"
    import_dir.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path / "sessions", model=_model(), persist=True)
    original = asyncio.run(runtime.create_session(cwd=str(project_root)))
    original.session_manager.append_message(_user_message("original"))

    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(project_root), persist=True)
    imported_manager.append_message(_user_message("imported"))
    imported_file = imported_manager.session_file
    assert imported_file is not None

    result = asyncio.run(runtime.importFromJsonl(str(imported_file)))
    current = runtime.get_current_session()

    assert result == {"cancelled": False}
    assert current is not None
    assert current is not original
    assert current.session_manager.session_file == (tmp_path / "sessions" / imported_file.name).resolve()
    assert current.session_manager.session_file.exists()
    assert [message.content[0].text for message in current.get_session_context().messages] == ["imported"]


def test_runtime_import_from_jsonl_does_not_overwrite_existing_same_name_session(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    import_dir = tmp_path / "imports"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    import_dir.mkdir()
    runtime = create_agent_session_runtime(session_dir=session_dir, model=_model(), persist=True)
    existing = asyncio.run(runtime.create_session(cwd=str(project_root)))
    existing.session_manager.append_message(_user_message("existing session"))
    existing_file = existing.session_manager.session_file
    assert existing_file is not None

    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(project_root), persist=True)
    imported_manager.append_message(_user_message("imported same basename"))
    imported_file = imported_manager.session_file
    assert imported_file is not None
    import_source = import_dir / existing_file.name
    imported_file.rename(import_source)

    result = asyncio.run(runtime.importFromJsonl(str(import_source)))
    current = runtime.get_current_session()
    reloaded_existing = SessionManager.open(existing_file)

    assert result == {"cancelled": False}
    assert current is not None
    assert current.session_manager.session_file != existing_file
    assert current.session_manager.session_file is not None
    assert current.session_manager.session_file.exists()
    assert [message.content[0].text for message in current.session_manager.build_session_context().messages] == [
        "imported same basename"
    ]
    assert [message.content[0].text for message in reloaded_existing.build_session_context().messages] == [
        "existing session"
    ]


def test_runtime_import_from_jsonl_retries_when_unique_destination_is_claimed_before_copy(
    tmp_path,
    monkeypatch,
) -> None:
    import errno

    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.runtime import agent_session_runtime as runtime_module
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    import_dir = tmp_path / "imports"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    import_dir.mkdir()
    runtime = create_agent_session_runtime(session_dir=session_dir, model=_model(), persist=True)
    existing = asyncio.run(runtime.create_session(cwd=str(project_root)))
    existing.session_manager.append_message(_user_message("existing session"))
    existing_file = existing.session_manager.session_file
    assert existing_file is not None

    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(project_root), persist=True)
    imported_manager.append_message(_user_message("imported after race"))
    imported_file = imported_manager.session_file
    assert imported_file is not None
    import_source = import_dir / existing_file.name
    imported_file.rename(import_source)

    real_copy = runtime_module._copy_import_file
    copy_attempts: list[Path] = []

    def _copy_with_external_race(source: Path, destination: Path) -> None:
        copy_attempts.append(destination)
        if len(copy_attempts) == 1:
            destination.write_text("external winner\n", encoding="utf-8")
            raise FileExistsError(errno.EEXIST, "File exists", str(destination))
        real_copy(source, destination)

    monkeypatch.setattr(runtime_module, "_copy_import_file", _copy_with_external_race)

    result = asyncio.run(runtime.importFromJsonl(str(import_source)))
    current = runtime.get_current_session()
    stem = existing_file.stem
    suffix = existing_file.suffix

    assert result == {"cancelled": False}
    assert current is not None
    assert copy_attempts == [
        (session_dir / f"{stem}-import-1{suffix}").resolve(),
        (session_dir / f"{stem}-import-2{suffix}").resolve(),
    ]
    assert copy_attempts[0].read_text(encoding="utf-8") == "external winner\n"
    assert current.session_manager.session_file == copy_attempts[1]
    assert [message.content[0].text for message in current.session_manager.build_session_context().messages] == [
        "imported after race"
    ]


def test_runtime_import_from_jsonl_race_retry_emits_before_switch_once_for_final_destination(
    tmp_path,
    monkeypatch,
) -> None:
    import errno

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.runtime import agent_session_runtime as runtime_module
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.session_id = manager.get_header().id

        def set_extension_runtime_host(self, _host) -> None:
            return None

        async def start_extension_runtime(self, *, reason: str) -> None:
            del reason

        async def dispose(self) -> None:
            return None

    project_root = tmp_path / "project"
    import_dir = tmp_path / "imports"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    import_dir.mkdir()
    seen_targets: list[str | None] = []

    def _before_switch(event, ctx):
        del ctx
        seen_targets.append(event.target_session_file)
        return None

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={"session_before_switch": [_before_switch]},
            )
        ]
    )
    runtime = AgentSessionRuntime(
        session_dir=session_dir,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=True,
    )
    existing = asyncio.run(runtime.create_session(cwd=str(project_root)))
    existing.session_manager.append_message(_user_message("existing session"))
    existing_file = existing.session_manager.session_file
    assert existing_file is not None

    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(project_root), persist=True)
    imported_manager.append_message(_user_message("imported after race"))
    imported_file = imported_manager.session_file
    assert imported_file is not None
    import_source = import_dir / existing_file.name
    imported_file.rename(import_source)

    real_copy = runtime_module._copy_import_file
    copy_attempts: list[Path] = []

    def _copy_with_external_race(source: Path, destination: Path) -> None:
        copy_attempts.append(destination)
        if len(copy_attempts) == 1:
            destination.write_text("external winner\n", encoding="utf-8")
            raise FileExistsError(errno.EEXIST, "File exists", str(destination))
        real_copy(source, destination)

    monkeypatch.setattr(runtime_module, "_copy_import_file", _copy_with_external_race)

    result = asyncio.run(runtime.importFromJsonl(str(import_source)))
    current = runtime.get_current_session()
    final_destination = copy_attempts[1]

    assert result == {"cancelled": False}
    assert current is not None
    assert current.session_manager.session_file == final_destination
    assert seen_targets == [str(final_destination)]


def test_runtime_import_from_jsonl_cleans_copied_file_when_stored_cwd_is_missing(tmp_path) -> None:
    import pytest

    from loushang.coding.bootstrap import create_agent_session_runtime
    from loushang.coding.runtime import MissingSessionCwdError
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    missing_cwd = tmp_path / "missing-project"
    import_dir = tmp_path / "imports"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    import_dir.mkdir()
    runtime = create_agent_session_runtime(session_dir=session_dir, model=_model(), persist=True)
    current = asyncio.run(runtime.create_session(cwd=str(project_root)))
    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(missing_cwd), persist=True)
    imported_manager.append_message(_user_message("missing cwd import"))
    imported_file = imported_manager.session_file
    assert imported_file is not None

    with pytest.raises(MissingSessionCwdError):
        asyncio.run(runtime.importFromJsonl(str(imported_file)))

    assert runtime.get_current_session() is current
    assert imported_file.exists()
    assert (session_dir / imported_file.name).exists() is False


def test_runtime_import_from_jsonl_records_failure_diagnostic(tmp_path) -> None:
    import pytest

    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.runtime import AgentSessionRuntime, MissingSessionCwdError
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.extension_runner = None
            self.diagnostics_service = None
            self.session_id = manager.get_header().id

        def set_extension_runtime_host(self, _host) -> None:
            return None

        async def start_extension_runtime(self, *, reason: str) -> None:
            del reason

        async def dispose(self) -> None:
            return None

    project_root = tmp_path / "project"
    missing_cwd = tmp_path / "missing-project"
    import_dir = tmp_path / "imports"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    import_dir.mkdir()
    diagnostics_service = DiagnosticsService()
    runtime = AgentSessionRuntime(
        session_dir=session_dir,
        session_factory=DummySession,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    current = asyncio.run(runtime.create_session(cwd=str(project_root)))
    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(missing_cwd), persist=True)
    imported_file = imported_manager.session_file
    assert imported_file is not None

    with pytest.raises(MissingSessionCwdError):
        asyncio.run(runtime.importFromJsonl(str(imported_file)))

    records = diagnostics_service.get_diagnostics(query=DiagnosticsQuery(code="session_import_failed"))

    assert runtime.get_current_session() is current
    assert len(records) == 1
    assert records[0].session_id == current.session_id
    assert records[0].details["operation"] == "import_from_jsonl"
    assert records[0].details["input_path"] == str(imported_file)
    assert records[0].details["source_path"] == str(imported_file.resolve())
    assert records[0].details["target_session_file"] == str((session_dir / imported_file.name).resolve())
    assert records[0].details["cwd_override"] is None


def test_runtime_restore_rejects_session_when_stored_cwd_is_missing(tmp_path) -> None:
    import pytest

    from loushang.coding.runtime import AgentSessionRuntime, MissingSessionCwdError
    from loushang.coding.store import SessionManager

    missing_cwd = tmp_path / "missing-project"
    manager = SessionManager.new(session_dir=tmp_path, cwd=str(missing_cwd), persist=True)
    session_file = manager.session_file
    assert session_file is not None
    created: list[SessionManager] = []

    def _factory(next_manager: SessionManager):
        created.append(next_manager)
        return object()

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)

    with pytest.raises(MissingSessionCwdError) as exc_info:
        asyncio.run(runtime.restore_session(session_file))

    assert exc_info.value.issue.session_cwd == str(missing_cwd)
    assert exc_info.value.issue.session_file == session_file
    assert created == []
    assert runtime.get_current_session() is None


def test_runtime_restore_session_records_failure_diagnostic(tmp_path) -> None:
    import pytest

    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.runtime import AgentSessionRuntime, MissingSessionCwdError
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.extension_runner = None
            self.diagnostics_service = None
            self.session_id = manager.get_header().id

        def set_extension_runtime_host(self, _host) -> None:
            return None

        async def start_extension_runtime(self, *, reason: str) -> None:
            del reason

        async def dispose(self) -> None:
            return None

    project_root = tmp_path / "project"
    missing_cwd = tmp_path / "missing-project"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    diagnostics_service = DiagnosticsService()
    target_manager = SessionManager.new(session_dir=session_dir, cwd=str(missing_cwd), persist=True)
    target_file = target_manager.session_file
    assert target_file is not None
    runtime = AgentSessionRuntime(
        session_dir=session_dir,
        session_factory=DummySession,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    current = asyncio.run(runtime.create_session(cwd=str(project_root)))

    with pytest.raises(MissingSessionCwdError):
        asyncio.run(runtime.restore_session(target_file))

    records = diagnostics_service.get_diagnostics(query=DiagnosticsQuery(code="session_restore_failed"))

    assert runtime.get_current_session() is current
    assert len(records) == 1
    assert records[0].session_id == current.session_id
    assert records[0].details["operation"] == "restore_session"
    assert records[0].details["session_ref"] == str(target_file)
    assert records[0].details["target_session_file"] == str(target_file.resolve())
    assert records[0].details["fallback_cwd"] is None
    assert records[0].details["missing_cwd"] == "error"


def test_runtime_restore_can_fallback_when_stored_cwd_is_missing(tmp_path) -> None:
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    missing_cwd = tmp_path / "missing-project"
    project_root.mkdir()
    manager = SessionManager.new(session_dir=tmp_path, cwd=str(missing_cwd), persist=True)
    manager.append_message(_user_message("hello"))
    session_file = manager.session_file
    assert session_file is not None
    created: list[SessionManager] = []

    class DummySession:
        def __init__(self, next_manager: SessionManager) -> None:
            self.session_manager = next_manager
            self.extension_runner = None
            self.diagnostics_service = None
            self.session_id = next_manager.get_header().id

        def set_extension_runtime_host(self, _host) -> None:
            return None

        async def dispose(self) -> None:
            return None

    def _factory(next_manager: SessionManager):
        created.append(next_manager)
        return DummySession(next_manager)

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)

    restored = asyncio.run(
        runtime.restore_session(
            session_file,
            fallback_cwd=project_root,
            missing_cwd="fallback",
        )
    )

    assert restored.session_manager.get_cwd() == str(project_root.resolve())
    assert created == [restored.session_manager]


def test_runtime_import_from_jsonl_cwd_override_bypasses_missing_stored_cwd(tmp_path) -> None:
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    missing_cwd = tmp_path / "missing-project"
    import_dir = tmp_path / "imports"
    project_root.mkdir()
    import_dir.mkdir()
    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(missing_cwd), persist=True)
    imported_manager.append_message(_user_message("imported"))
    imported_file = imported_manager.session_file
    assert imported_file is not None

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.extension_runner = None
            self.diagnostics_service = None
            self.session_id = manager.get_header().id

        def set_extension_runtime_host(self, _host) -> None:
            return None

        async def start_extension_runtime(self, *, reason: str) -> None:
            del reason

        async def dispose(self) -> None:
            return None

    runtime = AgentSessionRuntime(session_dir=tmp_path / "sessions", session_factory=DummySession, persist=True)

    result = asyncio.run(runtime.importFromJsonl(str(imported_file), cwd_override=str(project_root)))
    current = runtime.get_current_session()

    assert result == {"cancelled": False}
    assert current is not None
    assert current.session_manager.get_cwd() == str(project_root.resolve())
    assert [message.content[0].text for message in current.session_manager.build_session_context().messages] == ["imported"]


def test_runtime_import_from_jsonl_respects_before_switch_cancellation(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    project_root.mkdir()
    import_dir = tmp_path / "imports"
    import_dir.mkdir()
    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(project_root), persist=True)
    imported_manager.append_message(_user_message("imported"))
    imported_file = imported_manager.session_file
    assert imported_file is not None
    events: list[str | None] = []

    def _cancel_switch(event, ctx):
        del ctx
        events.append(event.target_session_file)
        return SessionActionDecision(cancel=True)

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="demo",
                        source_path=Path("/tmp/demo.py"),
                        hooks={"session_before_switch": [_cancel_switch]},
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path / "sessions", session_factory=_factory, persist=True)
    current = asyncio.run(runtime.create_session(cwd=str(project_root)))

    result = asyncio.run(runtime.importFromJsonl(str(imported_file)))

    assert result == {"cancelled": True}
    assert runtime.get_current_session() is current
    assert events == [str((tmp_path / "sessions" / imported_file.name).resolve())]
    assert not (tmp_path / "sessions" / imported_file.name).exists()


def test_runtime_import_from_jsonl_records_before_switch_failure_and_flushes_index(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    project_root = tmp_path / "project"
    import_dir = tmp_path / "imports"
    session_dir = tmp_path / "sessions"
    project_root.mkdir()
    import_dir.mkdir()
    diagnostics_service = DiagnosticsService()

    imported_manager = SessionManager.new(session_dir=import_dir, cwd=str(project_root), persist=True)
    imported_manager.append_message(_user_message("imported"))
    imported_file = imported_manager.session_file
    assert imported_file is not None

    def _before_switch(event, ctx):
        del event, ctx
        raise RuntimeError("before switch boom")

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            diagnostics_service=diagnostics_service,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="broken",
                        source_path=Path("/tmp/broken.py"),
                        hooks={"session_before_switch": [_before_switch]},
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(
        session_dir=session_dir,
        session_factory=_factory,
        persist=True,
        diagnostics_service=diagnostics_service,
        auto_refresh_session_index=True,
        session_index_flush_delay=60.0,
    )

    async def scenario() -> None:
        await runtime.create_session(cwd=str(project_root))
        result = await runtime.importFromJsonl(str(imported_file))
        assert result == {"cancelled": False}
        await runtime.drain_session_index_flush()

    asyncio.run(scenario())
    current = runtime.get_current_session()
    records = diagnostics_service.get_diagnostics(
        query=DiagnosticsQuery(code="extension_session_before_switch_failed")
    )

    assert current is not None
    assert current.session_manager.session_file == (session_dir / imported_file.name).resolve()
    assert current.session_id in {summary.session_id for summary in SessionManager.load_index(session_dir)}
    assert len(records) == 1
    assert records[0].message == "Extension hook 'session_before_switch' failed: before switch boom"


def test_runtime_pi_style_lifecycle_aliases_report_cancellation(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    def _cancel_switch(event, ctx):
        del event, ctx
        return SessionActionDecision(cancel=True)

    def _cancel_fork(event, ctx):
        del event, ctx
        return SessionActionDecision(cancel=True)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={
                    "session_before_switch": [_cancel_switch],
                    "session_before_fork": [_cancel_fork],
                },
            )
        ]
    )
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()
    current = asyncio.run(runtime.create_session(cwd=str(project)))
    entry_id = current.session_manager.append_message(_user_message("root"))

    assert asyncio.run(runtime.newSession()) == {"cancelled": True}
    assert asyncio.run(runtime.fork(entry_id, {"position": "at"})) == {"cancelled": True}
    assert runtime.get_current_session() is current
    assert current.disposed is False


def test_extension_command_context_fork_uses_runtime_host(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    results: list[object] = []

    async def _fork_command(args: str, ctx):
        result = await ctx.fork(args, {"position": "at"})
        results.append(result)

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="fork-ext",
                        source_path=Path("/tmp/fork-ext.py"),
                        commands={
                            "fork": RegisteredCommand(
                                name="fork",
                                handler=_fork_command,
                                description="Fork the session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    session.session_manager.append_message(_user_message("tail"))

    result = asyncio.run(session.execute_command_async("fork", second_id))
    forked = runtime.get_current_session()

    assert result.result is None
    assert results == [{"cancelled": False}]
    assert forked is not None
    assert forked is not session
    assert [entry.id for entry in forked.session_manager.get_branch()] == [first_id, second_id]


def test_extension_command_context_fork_supports_before_position(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    results: list[object] = []
    seen_branches: list[list[str]] = []

    async def _fork_command(args: str, ctx):
        result = await ctx.fork(args, {"position": "before"})
        results.append(result)

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="fork-ext",
                        source_path=Path("/tmp/fork-ext.py"),
                        commands={
                            "fork": RegisteredCommand(
                                name="fork",
                                handler=_fork_command,
                                description="Fork the session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    third_id = session.session_manager.append_message(_user_message("tail"))

    result = asyncio.run(session.execute_command_async("fork", third_id))
    forked = runtime.get_current_session()
    assert forked is not None
    seen_branches.append([entry.id for entry in forked.session_manager.get_branch()])

    assert result.result is None
    assert results == [{"cancelled": False, "selected_text": "tail", "selectedText": "tail"}]
    assert forked is not session
    assert seen_branches == [[first_id, second_id]]


def test_extension_command_context_fork_defaults_to_before_position(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    results: list[object] = []

    async def _fork_command(args: str, ctx):
        results.append(await ctx.fork(args))

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="fork-ext",
                        source_path=Path("/tmp/fork-ext.py"),
                        commands={
                            "fork": RegisteredCommand(
                                name="fork",
                                handler=_fork_command,
                                description="Fork the session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    third_id = session.session_manager.append_message(_user_message("tail"))

    result = asyncio.run(session.execute_command_async("fork", third_id))
    forked = runtime.get_current_session()

    assert result.result is None
    assert results == [{"cancelled": False, "selected_text": "tail", "selectedText": "tail"}]
    assert forked is not None
    assert [entry.id for entry in forked.session_manager.get_branch()] == [first_id, second_id]


def test_extension_command_context_fork_before_runs_with_session_on_new_fork(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    seen: list[tuple[str, list[str]]] = []

    async def _fork_command(args: str, ctx):
        async def _with_session(replaced_ctx):
            seen.append(
                (
                    replaced_ctx.cwd,
                    [
                        entry.id
                        for entry in replaced_ctx.sessionManager.get_branch()
                    ],
                )
            )

        await ctx.fork(args, {"position": "before", "withSession": _with_session})

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="fork-ext",
                        source_path=Path("/tmp/fork-ext.py"),
                        commands={
                            "fork": RegisteredCommand(
                                name="fork",
                                handler=_fork_command,
                                description="Fork the session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    first_id = session.session_manager.append_message(_user_message("root"))
    second_id = session.session_manager.append_message(_assistant_message("answer"))
    third_id = session.session_manager.append_message(_user_message("tail"))

    result = asyncio.run(session.execute_command_async("fork", third_id))

    assert result.result is None
    assert seen == [(str(project.resolve()), [first_id, second_id])]


def test_extension_command_context_new_session_uses_runtime_host(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    callback_events: list[tuple[str, object]] = []

    async def _new_command(args: str, ctx):
        del args

        async def _setup(manager):
            callback_events.append(("setup", manager.get_cwd()))
            manager.append_message(_user_message("initialized"))

        async def _with_session(replaced_ctx):
            callback_events.append(("withSession", (replaced_ctx.cwd, replaced_ctx.sessionManager is not None)))

        await ctx.newSession({"parentSession": "parent-1", "setup": _setup, "withSession": _with_session})

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="new-ext",
                        source_path=Path("/tmp/new-ext.py"),
                        commands={
                            "new": RegisteredCommand(
                                name="new",
                                handler=_new_command,
                                description="New session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))

    result = asyncio.run(session.execute_command_async("new", ""))
    created = runtime.get_current_session()

    assert result.result is None
    assert created is not None
    assert created is not session
    assert created.session_manager.get_header().parent_session == "parent-1"
    assert created.session_manager.get_cwd() == str(project.resolve())
    assert [message.content[0].text for message in created.get_session_context().messages] == ["initialized"]
    assert callback_events == [
        ("setup", str(project.resolve())),
        ("withSession", (str(project.resolve()), True)),
    ]


def test_extension_command_new_session_with_session_gets_fresh_context_and_stales_old_context(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    events: list[tuple[str, object]] = []

    async def _new_command(args: str, ctx):
        del args
        old_ctx = ctx

        async def _with_session(replaced_ctx):
            events.append(("fresh", (replaced_ctx.cwd, replaced_ctx.sessionManager is not None)))
            try:
                old_ctx.cwd
            except RuntimeError as exc:
                events.append(("stale", str(exc)))

        await ctx.newSession({"withSession": _with_session})

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="new-ext",
                        source_path=Path("/tmp/new-ext.py"),
                        commands={
                            "new": RegisteredCommand(
                                name="new",
                                handler=_new_command,
                                description="New session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))

    result = asyncio.run(session.execute_command_async("new", ""))

    assert result.result is None
    assert events == [
        ("fresh", (str(project.resolve()), True)),
        ("stale", "Extension context is stale after session replacement or shutdown."),
    ]


def test_replaced_session_context_send_message_becomes_stale_after_next_replacement(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    import pytest

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    captured: dict[str, object] = {}

    async def _new_command(args: str, ctx):
        del args

        async def _with_session(replaced_ctx):
            captured["ctx"] = replaced_ctx
            await replaced_ctx.sendMessage({"customType": "demo", "content": "fresh", "display": True})

        await ctx.newSession({"withSession": _with_session})

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="new-ext",
                        source_path=Path("/tmp/new-ext.py"),
                        commands={
                            "new": RegisteredCommand(
                                name="new",
                                handler=_new_command,
                                description="New session",
                            )
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))

    result = asyncio.run(session.execute_command_async("new", ""))
    replaced_ctx = captured["ctx"]
    current = runtime.get_current_session()
    assert result.result is None
    assert current is not None
    assert [entry.custom_type for entry in current.session_manager.get_entries()] == ["demo"]

    asyncio.run(runtime.newSession())

    with pytest.raises(RuntimeError, match="stale"):
        asyncio.run(replaced_ctx.sendMessage({"customType": "demo", "content": "stale", "display": True}))
    with pytest.raises(RuntimeError, match="stale"):
        asyncio.run(replaced_ctx.sendUserMessage("stale user text"))


def test_agent_session_exposes_pi_style_replaced_session_context(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    project = tmp_path / "project"
    project.mkdir()
    session = AgentSession(
        agent=Agent(),
        session_manager=SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True),
        extension_runner=ExtensionRunner([LoadedExtension(name="demo", source_path=Path("/tmp/demo.py"))]),
    )

    context = session.createReplacedSessionContext()

    assert context.cwd == str(project.resolve())
    assert context.sessionManager is session.session_manager
    assert context.getSessionName() is None


def test_extension_command_context_switch_session_uses_runtime_host(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    callback_events: list[tuple[str, object]] = []

    async def _switch_command(args: str, ctx):
        async def _with_session(replaced_ctx):
            callback_events.append(("withSession", (replaced_ctx.cwd, replaced_ctx.sessionManager is not None)))

        await ctx.switchSession(args, {"withSession": _with_session})

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="switch-ext",
                        source_path=Path("/tmp/switch-ext.py"),
                        commands={
                            "switch": RegisteredCommand(
                                name="switch",
                                handler=_switch_command,
                                description="Switch session",
                            )
                        },
                    )
                ]
            ),
        )

    project = tmp_path / "project"
    project.mkdir()
    first_manager = SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True)
    second_manager = SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True)
    second_manager.append_message(_user_message("restored"))
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=_factory,
        persist=True,
        current_session=_factory(first_manager),
    )
    session = runtime.get_current_session()
    assert session is not None

    result = asyncio.run(session.execute_command_async("switch", str(second_manager.session_file)))
    switched = runtime.get_current_session()

    assert result.result is None
    assert switched is not None
    assert switched is not session
    assert [message.content[0].text for message in switched.get_session_context().messages] == ["restored"]
    assert callback_events == [("withSession", (str(project.resolve()), True))]


def test_extension_command_replacement_callbacks_require_async_callables(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.diagnostics import DiagnosticsService
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, RegisteredCommand
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    async def _new_command(args: str, ctx):
        del args

        def _with_session(replaced_ctx):
            del replaced_ctx

        await ctx.newSession({"withSession": _with_session})

    diagnostics_service = DiagnosticsService()

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            diagnostics_service=diagnostics_service,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="new-ext",
                        source_path=Path("/tmp/new-ext.py"),
                        commands={"new": RegisteredCommand(name="new", handler=_new_command)},
                    )
                ]
            ),
        )

    project = tmp_path / "project"
    project.mkdir()
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=_factory,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    session = asyncio.run(runtime.create_session(cwd=str(project)))

    result = asyncio.run(session.execute_command_async("new", ""))

    assert result is not None
    assert result.result is None
    assert [diagnostic.code for diagnostic in diagnostics_service.get_diagnostics()] == ["extension_command_failed"]


def test_runtime_exposes_diagnostics_snapshot(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime, create_services
    from loushang.coding.diagnostics import DiagnosticsQuery

    services = create_services()
    services.diagnostics_service.record(
        services.diagnostics_service.normalize_exception(
            code="startup_warning",
            exc="heads up",
            phase="startup",
            source="bootstrap",
            level="warning",
        )
    )
    services.diagnostics_service.record(
        services.diagnostics_service.normalize_exception(
            code="runtime_error",
            exc="boom",
            phase="runtime",
            source="session",
            level="error",
        )
    )

    runtime = create_agent_session_runtime(
        session_dir=tmp_path,
        model=_model(),
        services=services,
        persist=False,
    )

    assert [record.code for record in runtime.get_last_diagnostics()] == [
        "startup_warning",
        "runtime_error",
    ]
    assert [record.code for record in runtime.get_diagnostics(DiagnosticsQuery(phase="runtime", source="session"))] == [
        "runtime_error"
    ]
    assert runtime.get_last_error_report() is not None
    assert runtime.get_last_error_report().primary.code == "runtime_error"


def test_runtime_exposes_current_session_diagnostics(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime, create_services
    from loushang.coding.diagnostics import DiagnosticsQuery

    services = create_services()
    runtime = create_agent_session_runtime(
        session_dir=tmp_path,
        model=_model(),
        services=services,
        persist=False,
    )
    session = asyncio.run(runtime.create_session(cwd=str(tmp_path)))
    services.diagnostics_service.record(
        services.diagnostics_service.normalize_exception(
            code="current_runtime_error",
            exc="boom",
            phase="runtime",
            source="session",
            session_id=session.session_id,
        )
    )
    services.diagnostics_service.record(
        services.diagnostics_service.normalize_exception(
            code="other_runtime_error",
            exc="other",
            phase="runtime",
            source="session",
            session_id="other-session",
        )
    )

    assert [record.code for record in runtime.get_session_diagnostics()] == ["current_runtime_error"]
    assert [
        record.code for record in runtime.get_session_diagnostics(DiagnosticsQuery(code="current_runtime_error"))
    ] == ["current_runtime_error"]
    summary = runtime.get_session_diagnostics_summary()
    assert summary.total_count == 1
    assert summary.by_code == {"current_runtime_error": 1}
    assert summary.latest_error is not None
    assert summary.latest_error.code == "current_runtime_error"


def test_agent_session_runtime_create_restore_and_fork_reconstruct_extension_start_hooks(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    events: list[str] = []

    def _session_start(event, ctx):
        del event
        events.append(ctx.cwd)

    def _factory(manager: SessionManager) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="demo",
                        source_path=Path("/tmp/demo.py"),
                        hooks={"session_start": [_session_start]},
                    )
                ]
                ),
            )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    session = asyncio.run(runtime.create_session(cwd=str(project)))
    restored = asyncio.run(runtime.restore_session(session.session_file))
    restored.session_manager.append_message(_user_message("branch me"))
    fork_entry_id = restored.session_manager.get_entries()[0].id
    asyncio.run(runtime.fork_session(fork_entry_id))

    assert events == [str(project.resolve()), str(project.resolve()), str(project.resolve())]


def test_runtime_replacement_emits_shutdown_before_next_session_start(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    events: list[tuple[str, str | None, str | None]] = []

    def _before_switch(event, ctx):
        del event, ctx
        events.append(("before_switch", None, None))

    def _session_shutdown(event, ctx):
        del ctx
        events.append(("shutdown", event.reason, event.target_session_file))

    def _session_start(event, ctx):
        del ctx
        events.append(("start", event.reason, event.previous_session_file))

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="demo",
                        source_path=Path("/tmp/demo.py"),
                        hooks={
                            "session_before_switch": [_before_switch],
                            "session_shutdown": [_session_shutdown],
                            "session_start": [_session_start],
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    first = asyncio.run(runtime.create_session(cwd=str(project)))
    first_session_file = first.session_manager.session_file
    assert first_session_file is not None
    events.clear()

    asyncio.run(runtime.new_session())

    assert runtime.get_current_session() is not None
    assert events == [
        ("before_switch", None, None),
        ("shutdown", "new", str(runtime.get_current_session().session_manager.session_file)),
        ("start", "new", str(first_session_file)),
    ]


def test_runtime_syncs_extension_lifecycle_failure_diagnostics(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.diagnostics import DiagnosticsService
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    diagnostics_service = DiagnosticsService()

    def _broken(name: str):
        def _hook(event, ctx):
            del event, ctx
            raise RuntimeError(f"{name} boom")

        return _hook

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            diagnostics_service=diagnostics_service,
            extension_runner=ExtensionRunner(
                [
                    LoadedExtension(
                        name="broken",
                        source_path=Path("/tmp/broken.py"),
                        hooks={
                            "session_before_switch": [_broken("before switch")],
                            "session_before_fork": [_broken("before fork")],
                            "session_shutdown": [_broken("shutdown")],
                        },
                    )
                ]
            ),
        )

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=_factory,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    project = tmp_path / "project"
    project.mkdir()

    first = asyncio.run(runtime.create_session(cwd=str(project)))
    second = asyncio.run(runtime.new_session())
    fork_entry_id = second.session_manager.append_message(_user_message("fork root"))
    asyncio.run(runtime.fork_session(fork_entry_id))

    records_by_code = {
        record.code: record
        for record in diagnostics_service.get_diagnostics()
        if record.code.startswith("extension_session_")
    }

    assert first is not second
    assert {
        "extension_session_before_switch_failed",
        "extension_session_before_fork_failed",
        "extension_session_shutdown_failed",
    }.issubset(records_by_code)
    assert records_by_code["extension_session_before_switch_failed"].message == (
        "Extension hook 'session_before_switch' failed: before switch boom"
    )
    assert records_by_code["extension_session_before_fork_failed"].message == (
        "Extension hook 'session_before_fork' failed: before fork boom"
    )
    assert records_by_code["extension_session_shutdown_failed"].message == (
        "Extension hook 'session_shutdown' failed: shutdown boom"
    )


def test_runtime_new_session_reuses_current_cwd_and_disposes_previous_session(tmp_path) -> None:
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()

    first = asyncio.run(runtime.create_session(cwd=str(project)))
    second = asyncio.run(runtime.new_session())

    assert runtime.get_current_session() is second
    assert second.session_manager.get_cwd() == str(project.resolve())
    assert first.disposed is True
    assert second.disposed is False
    assert second.session_manager.get_header().id != first.session_manager.get_header().id


def test_runtime_replacement_disposes_agent_session_local_resources(tmp_path) -> None:
    from loushang.agent import Agent
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
        )

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=True)
    project = tmp_path / "project"
    project.mkdir()
    first = asyncio.run(runtime.create_session(cwd=str(project)))
    first.footer_data_provider.set_extension_status("demo", "running")
    first.footer_data_provider.start_git_watcher(poll_interval_seconds=0.01, debounce_seconds=0)
    assert first.footer_data_provider.is_git_watcher_running()

    second = asyncio.run(runtime.new_session())

    assert runtime.get_current_session() is second
    assert second is not first
    assert first.footer_data_provider.get_extension_statuses() == {}
    assert first.footer_data_provider.is_git_watcher_running() is False


def test_runtime_replacement_records_shutdown_emit_failure_and_keeps_replacement(tmp_path) -> None:
    from pathlib import Path

    from loushang.agent import Agent
    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.extensions import ExtensionRunner, LoadedExtension
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.session import AgentSession
    from loushang.coding.store import SessionManager

    class BrokenShutdownRunner(ExtensionRunner):
        async def emit_session_shutdown(self, event) -> None:
            del event
            raise RuntimeError("shutdown transport boom")

    diagnostics_service = DiagnosticsService()

    def _factory(manager: SessionManager, *, session_start_event=None) -> AgentSession:
        return AgentSession(
            agent=Agent(),
            session_manager=manager,
            session_start_event=session_start_event,
            diagnostics_service=diagnostics_service,
            extension_runner=BrokenShutdownRunner(
                [LoadedExtension(name="demo", source_path=Path("/tmp/demo.py"))]
            ),
        )

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=_factory,
        persist=True,
        diagnostics_service=diagnostics_service,
    )
    project = tmp_path / "project"
    project.mkdir()
    first = asyncio.run(runtime.create_session(cwd=str(project)))
    first.footer_data_provider.set_extension_status("demo", "running")

    second = asyncio.run(runtime.new_session())
    records = diagnostics_service.get_diagnostics(query=DiagnosticsQuery(code="session_shutdown_failed"))

    assert runtime.get_current_session() is second
    assert second is not first
    assert first.footer_data_provider.get_extension_statuses() == {}
    assert len(records) == 1
    assert records[0].message == "shutdown transport boom"
    assert records[0].session_id == first.session_id
    assert records[0].details["reason"] == "new"
    assert records[0].details["target_session_file"] == str(second.session_manager.session_file)


def test_runtime_new_session_factory_failure_keeps_current_session_alive(tmp_path) -> None:
    import pytest

    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    created = 0

    def _factory(manager: SessionManager) -> DummySession:
        nonlocal created
        created += 1
        if created == 2:
            raise RuntimeError("factory boom")
        return DummySession(manager)

    runtime = AgentSessionRuntime(session_dir=tmp_path, session_factory=_factory, persist=False)
    project = tmp_path / "project"
    project.mkdir()
    first = asyncio.run(runtime.create_session(cwd=str(project)))

    with pytest.raises(RuntimeError, match="factory boom"):
        asyncio.run(runtime.new_session())

    assert runtime.get_current_session() is first
    assert first.disposed is False


def test_runtime_replacements_are_serialized(tmp_path) -> None:
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.disposed = False
            self.dispose_calls = 0
            self.dispose_started: asyncio.Event | None = None
            self.dispose_release: asyncio.Event | None = None

        async def dispose(self) -> None:
            self.dispose_calls += 1
            self.disposed = True
            if self.dispose_started is not None:
                self.dispose_started.set()
            if self.dispose_release is not None:
                await self.dispose_release.wait()

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()

    async def scenario():
        first = await runtime.create_session(cwd=str(project))
        first.dispose_started = asyncio.Event()
        first.dispose_release = asyncio.Event()
        first_replacement = asyncio.create_task(runtime.new_session())
        await first.dispose_started.wait()
        second_replacement = asyncio.create_task(runtime.new_session())
        await asyncio.sleep(0)
        first.dispose_release.set()
        second, third = await asyncio.gather(first_replacement, second_replacement)
        return first, second, third

    first, second, third = asyncio.run(scenario())

    assert first.dispose_calls == 1
    assert second.dispose_calls == 1
    assert third.dispose_calls == 0
    assert runtime.get_current_session() is third


def test_runtime_dispose_records_session_index_flush_failure(tmp_path, monkeypatch) -> None:
    from loushang.coding.diagnostics import DiagnosticsQuery, DiagnosticsService
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    diagnostics_service = DiagnosticsService()
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager),
        persist=False,
        diagnostics_service=diagnostics_service,
        auto_refresh_session_index=True,
        session_index_flush_delay=60.0,
    )
    project = tmp_path / "project"
    project.mkdir()

    async def scenario() -> DummySession:
        session = await runtime.create_session(cwd=str(project))

        def _fail_refresh_index(cls, session_dir):
            del cls, session_dir
            raise RuntimeError("index boom")

        monkeypatch.setattr(SessionManager, "refresh_index", classmethod(_fail_refresh_index))
        await runtime.dispose()
        return session

    session = asyncio.run(scenario())
    records = diagnostics_service.get_diagnostics(query=DiagnosticsQuery(code="session_index_refresh_failed"))

    assert runtime.get_current_session() is None
    assert session.disposed is True
    assert len(records) == 1
    assert records[0].message == "index boom"
    assert records[0].details == {"all_sessions": False, "session_dir": str(tmp_path)}


def test_runtime_exposes_current_session_and_cwd_properties(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=False)

    session = asyncio.run(runtime.create_session(cwd=str(project)))

    assert runtime.session is session
    assert runtime.current_session is session
    assert runtime.cwd == str(project.resolve())


def test_runtime_replacement_callbacks_run_before_with_session(tmp_path) -> None:
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager) -> None:
            self.session_manager = manager
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()
    first = asyncio.run(runtime.create_session(cwd=str(project)))
    events: list[tuple[str, object]] = []

    async def _rebind(session):
        events.append(("rebind", session is runtime.get_current_session()))

    def _before_invalidate() -> None:
        events.append(("before", first.disposed))

    async def _with_session(ctx):
        events.append(("withSession", ctx.sessionManager is runtime.get_current_session().session_manager))

    runtime.set_rebind_session(_rebind)
    runtime.set_before_session_invalidate(_before_invalidate)

    asyncio.run(runtime.newSession({"withSession": _with_session}))

    assert events == [
        ("before", False),
        ("rebind", True),
        ("withSession", True),
    ]
    assert first.disposed is True


def test_runtime_restore_session_accepts_session_id(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)

    created = asyncio.run(runtime.create_session(cwd=str(project)))
    restored = asyncio.run(runtime.restore_session(created.session_id))

    assert restored.session_id == created.session_id
    assert restored.session_manager.get_cwd() == str(project.resolve())


def test_runtime_restore_session_accepts_session_id_prefix(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)

    created = asyncio.run(runtime.create_session(cwd=str(project)))
    restored = asyncio.run(runtime.restore_session(created.session_id[:8]))

    assert restored.session_id == created.session_id


def test_runtime_restore_session_rejects_ambiguous_session_id_prefix(tmp_path) -> None:
    import json

    import pytest

    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    project.mkdir()
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=True)
    timestamp = "2026-05-01T00:00:00Z"
    for session_id in ("abcdef01", "abcdef02"):
        (tmp_path / f"{timestamp}_{session_id}.jsonl").write_text(
            json.dumps(
                {
                    "type": "session",
                    "version": 3,
                    "id": session_id,
                    "timestamp": timestamp,
                    "cwd": str(project),
                    "parentSession": None,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="Ambiguous session reference"):
        asyncio.run(runtime.restore_session("abcdef"))


def test_runtime_create_session_normalizes_cwd_and_rejects_missing_paths(tmp_path) -> None:
    from loushang.coding.bootstrap import create_agent_session_runtime

    project = tmp_path / "project"
    nested = project / "nested"
    nested.mkdir(parents=True)
    runtime = create_agent_session_runtime(session_dir=tmp_path, model=_model(), persist=False)

    created = asyncio.run(runtime.create_session(cwd=str(nested / "..")))

    assert created.session_manager.get_cwd() == str(project.resolve())

    try:
        asyncio.run(runtime.create_session(cwd=str(tmp_path / "missing")))
    except FileNotFoundError as exc:
        assert exc.filename == str(tmp_path / "missing")
    else:
        raise AssertionError("create_session should reject missing cwd paths")


def test_runtime_new_session_respects_extension_before_switch_cancellation(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    seen: list[tuple[str, str, str | None]] = []

    def _before_switch(event, ctx):
        seen.append((event.reason, ctx.cwd, event.target_session_file))
        return SessionActionDecision(cancel=True)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={"session_before_switch": [_before_switch]},
            )
        ]
    )
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()

    first = asyncio.run(runtime.create_session(cwd=str(project)))
    second = asyncio.run(runtime.new_session())

    assert second is first
    assert runtime.get_current_session() is first
    assert first.disposed is False
    assert seen == [("new", str(project.resolve()), None)]


def test_runtime_fork_session_respects_extension_before_fork_cancellation(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    seen: list[str] = []

    def _before_fork(event, ctx):
        del ctx
        seen.append(event.entry_id)
        return SessionActionDecision(cancel=True)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={"session_before_fork": [_before_fork]},
            )
        ]
    )
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()

    current = asyncio.run(runtime.create_session(cwd=str(project)))
    first_entry_id = current.session_manager.append_message(_user_message("root"))
    forked = asyncio.run(runtime.fork_session(first_entry_id))

    assert forked is current
    assert runtime.get_current_session() is current
    assert current.disposed is False
    assert seen == [first_entry_id]


def test_runtime_new_session_allows_extension_non_cancel_decision(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    seen: list[tuple[str, str, str | None]] = []

    def _before_switch(event, ctx):
        del ctx
        seen.append((event.reason, event.cwd, event.target_session_file))
        return SessionActionDecision(cancel=False)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={"session_before_switch": [_before_switch]},
            )
        ]
    )
    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()

    first = asyncio.run(runtime.create_session(cwd=str(project)))
    second = asyncio.run(runtime.new_session())

    assert second is not first
    assert runtime.get_current_session() is second
    assert first.disposed is True
    assert seen == [("new", str(project.resolve()), None)]


def test_runtime_restore_session_allows_extension_non_cancel_decision(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    seen: list[tuple[str, str, str]] = []

    def _before_switch(event, ctx):
        del ctx
        seen.append((event.reason, event.cwd, event.target_session_file))
        return SessionActionDecision(cancel=False)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={"session_before_switch": [_before_switch]},
            )
        ]
    )

    project = tmp_path / "project"
    target = tmp_path / "target"
    project.mkdir()
    target.mkdir()
    current_manager = SessionManager.new(session_dir=tmp_path, cwd=str(project), persist=True)
    target_manager = SessionManager.new(session_dir=tmp_path, cwd=str(target), persist=True)
    target_manager.append_message(_user_message("from target"))

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=False,
        current_session=DummySession(current_manager, runner),
    )
    current = runtime.get_current_session()
    assert current is not None

    restored = asyncio.run(runtime.restore_session(target_manager.session_file))

    assert restored is not current
    assert current.disposed is True
    assert runtime.get_current_session() is restored
    assert isinstance(restored, DummySession)
    assert [entry.id for entry in restored.session_manager.get_entries()] == [target_manager.get_entries()[0].id]
    assert seen == [("resume", str(project.resolve()), str(target_manager.session_file))]


def test_runtime_fork_session_allows_extension_non_cancel_decision(tmp_path) -> None:
    from pathlib import Path

    from loushang.coding.extensions import ExtensionRunner, LoadedExtension, SessionActionDecision
    from loushang.coding.runtime import AgentSessionRuntime
    from loushang.coding.store import SessionManager

    class DummySession:
        def __init__(self, manager: SessionManager, runner: ExtensionRunner) -> None:
            self.session_manager = manager
            self.extension_runner = runner
            self.diagnostics_service = None
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    seen: list[tuple[str, str]] = []

    def _before_fork(event, ctx):
        del ctx
        seen.append((event.entry_id, event.cwd))
        return SessionActionDecision(cancel=False)

    runner = ExtensionRunner(
        [
            LoadedExtension(
                name="demo",
                source_path=Path("/tmp/demo.py"),
                hooks={"session_before_fork": [_before_fork]},
            )
        ]
    )

    runtime = AgentSessionRuntime(
        session_dir=tmp_path,
        session_factory=lambda manager: DummySession(manager, runner),
        persist=False,
    )
    project = tmp_path / "project"
    project.mkdir()

    current = asyncio.run(runtime.create_session(cwd=str(project)))
    fork_entry = current.session_manager.append_message(_user_message("root"))
    forked = asyncio.run(runtime.fork_session(fork_entry))

    assert forked is not current
    assert runtime.get_current_session() is forked
    assert current.disposed is True
    assert [entry.id for entry in forked.session_manager.get_branch()] == [fork_entry]
    assert seen == [(fork_entry, str(project.resolve()))]
