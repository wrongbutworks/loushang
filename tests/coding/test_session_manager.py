from __future__ import annotations


def test_append_entry_advances_leaf_id(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    entry_id = manager.append_session_info("demo")

    assert manager.get_leaf_id() == entry_id


def test_new_session_manager_has_header_and_no_leaf(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    assert manager.get_header().type == "session"
    assert manager.get_leaf_id() is None


def test_new_session_manager_accepts_custom_session_id(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=True,
        session_id="my-custom-id",
    )

    assert manager.get_header().id == "my-custom-id"
    assert manager.get_session_file() == tmp_path / f"{manager.get_header().timestamp.replace(':', '-').replace('.', '-')}_my-custom-id.jsonl"


def test_in_memory_session_manager_accepts_custom_session_id() -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.in_memory(cwd="/tmp/project", session_id="memory-session")

    assert manager.get_header().id == "memory-session"
    assert manager.get_session_file() is None


def test_new_session_manager_rejects_blank_custom_session_id(tmp_path) -> None:
    import pytest

    from loushang.coding.store import SessionManager

    with pytest.raises(ValueError, match="session_id must not be blank"):
        SessionManager.new(
            session_dir=tmp_path,
            cwd="/tmp/project",
            persist=False,
            session_id="  ",
        )


def test_branch_changes_active_leaf_without_losing_existing_path(tmp_path) -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    first_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        )
    )
    second_id = manager.append_message(
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="middle")],
            api="anthropic-messages",
            provider="faux",
            model="faux-model",
            response_id=None,
            usage=Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}),
            stop_reason="stop",
            error_message=None,
            timestamp=0.0,
        )
    )
    third_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="tail")],
            timestamp=0.0,
        )
    )

    manager.branch(first_id)
    branch_leaf_id = manager.append_session_info("forked")

    assert [entry.id for entry in manager.get_branch()] == [first_id, branch_leaf_id]
    assert [entry.id for entry in manager.get_branch(third_id)] == [first_id, second_id, third_id]
    assert manager.get_entry(branch_leaf_id).parent_id == first_id


def test_create_branched_session_persists_only_selected_path(tmp_path) -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=True,
    )

    first_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        )
    )
    second_id = manager.append_message(
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="answer")],
            api="anthropic-messages",
            provider="faux",
            model="faux-model",
            response_id=None,
            usage=Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}),
            stop_reason="stop",
            error_message=None,
            timestamp=0.0,
        )
    )
    manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="tail")],
            timestamp=0.0,
        )
    )

    branched_file = manager.create_branched_session(second_id)
    assert branched_file is not None

    forked = SessionManager.load(branched_file)

    assert [entry.id for entry in forked.get_branch()] == [first_id, second_id]
    assert forked.get_header().parent_session == str(manager.session_file)


def test_append_message_rejects_projected_summary_messages(tmp_path) -> None:
    import pytest

    from loushang.coding.message import BranchSummaryMessage, CompactionSummaryMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    with pytest.raises(ValueError):
        manager.append_message(
            BranchSummaryMessage(role="branchSummary", summary="done", from_id="b1", timestamp=0.0)
        )

    with pytest.raises(ValueError):
        manager.append_message(
            CompactionSummaryMessage(role="compactionSummary", summary="compact", tokens_before=10, timestamp=0.0)
        )


def test_session_manager_rejects_non_json_custom_metadata(tmp_path) -> None:
    from pathlib import Path

    import pytest

    from loushang.coding.store import SessionManager
    from loushang.protocol import JsonValueError

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    with pytest.raises(JsonValueError) as exc_info:
        manager.append_custom_entry("demo", {"path": Path("notes.txt")})

    assert exc_info.value.path == "custom_entry.data.path"


def test_branch_with_summary_creates_projected_branch_entry(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.message import BranchSummaryEntry
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    root_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        )
    )
    tail_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="tail")],
            timestamp=0.0,
        )
    )

    summary_id = manager.branch_with_summary(root_id, "forked away from tail")

    summary_entry = manager.get_entry(summary_id)

    assert isinstance(summary_entry, BranchSummaryEntry)
    assert manager.get_leaf_id() == summary_id
    assert summary_entry.parent_id == root_id
    assert summary_entry.from_id == root_id
    assert [entry.id for entry in manager.get_branch()] == [root_id, summary_id]
    assert [entry.id for entry in manager.get_branch(tail_id)] == [root_id, tail_id]
    assert [message.role for message in manager.build_session_context().messages] == ["user", "branchSummary"]


def test_get_tree_and_children_reflect_current_branches(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=False,
    )

    root_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        )
    )
    first_child_id = manager.append_session_info("main")
    manager.branch(root_id)
    second_child_id = manager.append_session_info("fork")

    assert manager.get_leaf_entry() is not None
    assert manager.get_leaf_entry().id == second_child_id
    assert [entry.id for entry in manager.get_children(root_id)] == [first_child_id, second_child_id]

    tree = manager.get_tree()

    assert [node.entry.id for node in tree] == [root_id]
    assert [child.entry.id for child in tree[0].children] == [first_child_id, second_child_id]


def test_labels_are_indexed_and_rebuilt_on_reload(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(
        session_dir=tmp_path,
        cwd="/tmp/project",
        persist=True,
    )

    root_id = manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="root")],
            timestamp=0.0,
        )
    )
    manager.append_label(root_id, "bookmark")

    assert manager.get_label(root_id) == "bookmark"
    assert manager.get_tree()[0].label == "bookmark"

    reloaded = SessionManager.load(manager.get_session_file())

    assert reloaded.get_label(root_id) == "bookmark"
    assert reloaded.get_tree()[0].label == "bookmark"


def test_list_skips_invalid_session_files(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="hello")],
            timestamp=0.0,
        )
    )

    (tmp_path / "broken.jsonl").write_text("not jsonl content\n", encoding="utf-8")
    (tmp_path / "not-session.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "bad-session-line.jsonl").write_text('{"type":"session","timestamp":"x","cwd":"/tmp"}\n{invalid}\n', encoding="utf-8")

    records = SessionManager.list(tmp_path)

    assert len(records) == 1
    assert records[0].session_id == manager.get_session_record().session_id


def test_session_summary_includes_context_metadata(tmp_path) -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    manager.append_session_info("Demo Session")
    manager.append_model_change("moonshot", "kimi-k2.5")
    manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="please inspect the repository")],
            timestamp=0.0,
        )
    )
    manager.append_message(
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="repository inspection complete")],
            api="anthropic-messages",
            provider="moonshot",
            model="kimi-k2.5",
            response_id=None,
            usage=Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}),
            stop_reason="stop",
            error_message=None,
            timestamp=0.0,
        )
    )

    summary = manager.get_session_summary()

    assert summary.session_id == manager.get_header().id
    assert summary.cwd == "/tmp/project"
    assert summary.name == "Demo Session"
    assert summary.message_count == 2
    assert summary.entry_count == 4
    assert summary.first_message == "please inspect the repository"
    assert summary.all_messages_text == "please inspect the repository repository inspection complete"
    assert summary.last_message_preview == "repository inspection complete"
    assert summary.model == {"provider": "moonshot", "model_id": "kimi-k2.5"}


def test_list_summaries_and_find_sessions_query_across_session_files(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager, SessionQuery

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-a", persist=True)
    first.append_session_info("Alpha")
    first.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="alpha repository task")],
            timestamp=0.0,
        )
    )

    second = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-b", persist=True, parent_session=str(first.get_session_file()))
    second.append_session_info("Beta")
    second.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="beta follow up")],
            timestamp=0.0,
        )
    )

    summaries = SessionManager.list_summaries(tmp_path)

    assert {summary.session_id for summary in summaries} == {first.get_header().id, second.get_header().id}
    assert [summary.name for summary in SessionManager.find_sessions(tmp_path, SessionQuery(cwd="/tmp/project-a"))] == ["Alpha"]
    assert [summary.name for summary in SessionManager.find_sessions(tmp_path, SessionQuery(name="bet"))] == ["Beta"]
    assert [summary.name for summary in SessionManager.find_sessions(tmp_path, SessionQuery(text="repository"))] == ["Alpha"]
    assert [summary.name for summary in SessionManager.find_sessions(tmp_path, SessionQuery(parent_session=str(first.get_session_file())))] == [
        "Beta"
    ]
    assert len(SessionManager.find_sessions(tmp_path, SessionQuery(limit=1))) == 1


def test_session_manager_rename_session_file_appends_session_info(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="hello")],
            timestamp=1000.0,
        )
    )
    session_file = manager.get_session_file()
    assert session_file is not None

    renamed = SessionManager.rename_session(session_file, "  Renamed Session  ")
    cleared = SessionManager.rename_session(session_file, "  ")

    assert renamed.name == "Renamed Session"
    assert cleared.name is None
    assert SessionManager.load(session_file).get_session_summary().name is None


def test_session_manager_delete_session_file_removes_file_and_lock(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    session_file = manager.get_session_file()
    assert session_file is not None
    lock_file = session_file.with_name(f"{session_file.name}.lock")
    SessionManager.load(session_file)
    assert lock_file.exists()

    assert SessionManager.delete_session(session_file) is True
    assert session_file.exists() is False
    assert lock_file.exists() is False
    assert SessionManager.delete_session(session_file) is False


def test_session_manager_rename_and_delete_refresh_existing_index(tmp_path) -> None:
    from loushang.coding.store import SessionManager

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    second = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    first_file = first.get_session_file()
    second_file = second.get_session_file()
    assert first_file is not None
    assert second_file is not None
    SessionManager.refresh_index(tmp_path)

    SessionManager.rename_session(first_file, "Indexed Name")
    renamed_index = SessionManager.list_indexed_summaries(tmp_path)
    SessionManager.delete_session(second_file)
    deleted_index = SessionManager.list_indexed_summaries(tmp_path)

    assert next(summary for summary in renamed_index if summary.session_id == first.get_header().id).name == "Indexed Name"
    assert {summary.session_id for summary in deleted_index} == {first.get_header().id}


def test_session_manager_rename_and_delete_survive_index_refresh_failure(tmp_path, monkeypatch) -> None:
    from loushang.coding.store import SessionManager

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    second = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    first_file = first.get_session_file()
    second_file = second.get_session_file()
    assert first_file is not None
    assert second_file is not None
    SessionManager.refresh_index(tmp_path)

    def _fail_refresh_index(cls, session_dir):
        del cls, session_dir
        raise RuntimeError("index boom")

    monkeypatch.setattr(SessionManager, "refresh_index", classmethod(_fail_refresh_index))

    renamed = SessionManager.rename_session(first_file, "Renamed Anyway")
    deleted = SessionManager.delete_session(second_file)

    assert renamed.name == "Renamed Anyway"
    assert deleted is True
    assert SessionManager.load(first_file).get_session_summary().name == "Renamed Anyway"
    assert second_file.exists() is False


def test_session_manager_delete_session_file_refuses_current_session_alias(tmp_path) -> None:
    import pytest

    from loushang.coding.store import SessionManager

    real_dir = tmp_path / "real"
    alias_dir = tmp_path / "alias"
    real_dir.mkdir()
    alias_dir.symlink_to(real_dir, target_is_directory=True)
    manager = SessionManager.new(session_dir=real_dir, cwd="/tmp/project", persist=True)
    session_file = manager.get_session_file()
    assert session_file is not None
    aliased_file = alias_dir / session_file.name

    with pytest.raises(ValueError, match="currently active session"):
        SessionManager.delete_session(aliased_file, current_session_file=session_file)

    assert session_file.exists() is True


def test_find_sessions_matches_parent_session_across_symlink_aliases(tmp_path) -> None:
    from loushang.coding.store import SessionManager, SessionQuery

    real_dir = tmp_path / "real"
    alias_a = tmp_path / "alias-a"
    alias_b = tmp_path / "alias-b"
    real_dir.mkdir()
    alias_a.symlink_to(real_dir, target_is_directory=True)
    alias_b.symlink_to(real_dir, target_is_directory=True)

    parent = SessionManager.new(session_dir=alias_a, cwd="/tmp/project", persist=True)
    parent_file = parent.get_session_file()
    assert parent_file is not None
    child = SessionManager.new(
        session_dir=alias_b,
        cwd="/tmp/project",
        parent_session=str(parent_file),
        persist=True,
    )
    child.append_session_info("Child")

    matched = SessionManager.find_sessions(real_dir, SessionQuery(parent_session=str(alias_b / parent_file.name)))

    assert [summary.session_id for summary in matched] == [child.get_header().id]


def test_find_sessions_supports_quoted_phrase_regex_and_named_filter(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager, SessionQuery

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    first.append_session_info("Named")
    first.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="node\n\n   cve was discussed")],
            timestamp=2000.0,
        )
    )
    second = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    second.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="bravery is not brave")],
            timestamp=3000.0,
        )
    )

    assert [summary.session_id for summary in SessionManager.find_sessions(tmp_path, SessionQuery(text='"node cve"'))] == [
        first.get_header().id
    ]
    assert [summary.session_id for summary in SessionManager.find_sessions(tmp_path, SessionQuery(text=r"re:\bbrave\b"))] == [
        second.get_header().id
    ]
    assert [summary.session_id for summary in SessionManager.find_sessions(tmp_path, SessionQuery(named=True))] == [
        first.get_header().id
    ]
    assert SessionManager.find_sessions(tmp_path, SessionQuery(text="re:(")) == []


def test_find_sessions_relevance_sort_scores_earlier_matches_before_recent(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager, SessionQuery

    early_match = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    early_match.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="brave xxxx")],
            timestamp=1000.0,
        )
    )
    later_match = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    later_match.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="xxxx brave")],
            timestamp=3000.0,
        )
    )

    result = SessionManager.find_sessions(tmp_path, SessionQuery(text='"brave"', sort_by="relevance"))

    assert [summary.session_id for summary in result] == [early_match.get_header().id, later_match.get_header().id]


def test_session_summary_searches_all_messages_and_uses_message_modified_time(tmp_path) -> None:
    from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
    from loushang.coding.store import SessionManager, SessionQuery

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-a", persist=True)
    first.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="initial alpha task")],
            timestamp=1000.0,
        )
    )
    first.append_message(
        AssistantMessage(
            role="assistant",
            content=[TextPart(type="text", text="middle-only searchable needle")],
            api="anthropic-messages",
            provider="faux",
            model="faux-model",
            response_id=None,
            usage=Usage(input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}),
            stop_reason="stop",
            error_message=None,
            timestamp=2000.0,
        )
    )
    first.append_session_info("Renamed Later")
    first.append_custom_entry("diagnostic", {"code": "later_metadata", "level": "warning"})

    second = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-b", persist=True)
    second.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="newer conversation")],
            timestamp=3000.0,
        )
    )

    summary = first.get_session_summary()

    assert summary.first_message == "initial alpha task"
    assert summary.all_messages_text == "initial alpha task middle-only searchable needle"
    assert summary.updated_at == "1970-01-01T00:33:20Z"
    assert [item.session_id for item in SessionManager.find_sessions(tmp_path, SessionQuery(text="middle-only"))] == [
        first.get_header().id
    ]
    assert [item.session_id for item in SessionManager.list_summaries(tmp_path)] == [
        second.get_header().id,
        first.get_header().id,
    ]


def test_session_metadata_accepts_message_timestamps_in_milliseconds(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager
    from loushang.observability import (
        get_problem_store,
        log_context,
        reset_observability,
    )

    session = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    session.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="millisecond timestamp")],
            timestamp=1_000_000_000_000.0,
        )
    )

    reset_observability()
    try:
        with log_context(session_id="session-1", cwd="/tmp/project", mode="metadata"):
            assert session.load_metadata().updated_at == "2001-09-09T01:46:40Z"

        records = get_problem_store().all()
        assert len(records) == 1
        assert records[0].code == "session_timestamp_normalized"
        assert records[0].severity == "warning"
        assert records[0].source == "session"
        assert records[0].recoverable is True
        assert records[0].details == {
            "normalized_timestamp": 1_000_000_000.0,
            "original_timestamp": 1_000_000_000_000.0,
            "unit": "milliseconds",
        }
        assert records[0].session_id == "session-1"
        assert records[0].mode == "metadata"
    finally:
        reset_observability()


def test_session_summary_indexes_diagnostic_custom_entries(tmp_path) -> None:
    from loushang.coding.store import SessionManager, SessionQuery

    clean = SessionManager.new(session_dir=tmp_path, cwd="/tmp/clean", persist=True)
    clean.append_session_info("Clean")

    flagged = SessionManager.new(session_dir=tmp_path, cwd="/tmp/flagged", persist=True)
    flagged.append_session_info("Flagged")
    flagged.append_custom_entry(
        "diagnostic",
        {
            "code": "model_auth_unresolved",
            "level": "warning",
            "message": "Provider demo has no configured API key.",
        },
    )
    flagged.append_custom_entry(
        "diagnostic",
        {
            "code": "assistant_response_error",
            "level": "error",
            "message": "provider failed",
        },
    )

    summary = flagged.get_session_summary()

    assert summary.has_diagnostics is True
    assert summary.diagnostic_count == 2
    assert summary.last_diagnostic_code == "assistant_response_error"
    assert summary.last_diagnostic_level == "error"
    assert [item.name for item in SessionManager.find_sessions(tmp_path, SessionQuery(has_diagnostics=True))] == [
        "Flagged"
    ]
    assert [item.name for item in SessionManager.find_sessions(tmp_path, SessionQuery(has_diagnostics=False))] == [
        "Clean"
    ]
    assert [item.name for item in SessionManager.find_sessions(tmp_path, SessionQuery(text="assistant_response_error"))] == [
        "Flagged"
    ]


def test_session_manager_writes_and_queries_session_index(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager, SessionQuery

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-a", persist=True)
    first.append_message(UserMessage(role="user", content=[TextPart(type="text", text="indexable alpha task")], timestamp=1000.0))

    nested_dir = tmp_path / "nested"
    nested = SessionManager.new(session_dir=nested_dir, cwd="/tmp/project-b", persist=True)
    nested.append_message(UserMessage(role="user", content=[TextPart(type="text", text="nested beta task")], timestamp=2000.0))

    root_summaries = SessionManager.refresh_index(tmp_path)
    nested_summaries = SessionManager.refresh_index(nested_dir)

    assert SessionManager.index_file(tmp_path).exists()
    assert [summary.session_id for summary in SessionManager.load_index(tmp_path)] == [
        summary.session_id for summary in root_summaries
    ]
    assert [summary.session_id for summary in SessionManager.find_indexed_sessions(tmp_path, SessionQuery(text="alpha"))] == [
        first.get_header().id
    ]
    assert [summary.session_id for summary in SessionManager.find_all_indexed_sessions(tmp_path, SessionQuery(text="beta"))] == [
        nested.get_header().id
    ]
    assert [summary.session_id for summary in SessionManager.list_all_indexed_summaries(tmp_path)] == [
        nested_summaries[0].session_id,
        root_summaries[0].session_id,
    ]


def test_session_manager_rebuilds_invalid_session_index(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    session = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    session.append_message(UserMessage(role="user", content=[TextPart(type="text", text="fresh index")], timestamp=1000.0))
    SessionManager.index_file(tmp_path).write_text("not-json\n", encoding="utf-8")

    summaries = SessionManager.list_indexed_summaries(tmp_path)

    assert [summary.session_id for summary in summaries] == [session.get_header().id]
    assert SessionManager.load_index(tmp_path)[0].session_id == session.get_header().id


def test_session_manager_preserves_corrupt_index_for_diagnostics(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    session = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=True)
    session.append_message(UserMessage(role="user", content=[TextPart(type="text", text="recover me")], timestamp=1000.0))
    index_file = SessionManager.index_file(tmp_path)
    index_file.write_text("not-json\n", encoding="utf-8")

    summaries = SessionManager.list_indexed_summaries(tmp_path)

    assert [summary.session_id for summary in summaries] == [session.get_header().id]
    corrupt_files = sorted(tmp_path.glob(".session-index.json.corrupt-*"))
    assert len(corrupt_files) == 1
    assert corrupt_files[0].read_text(encoding="utf-8") == "not-json\n"


def test_session_manager_rebuilds_stale_index_when_indexed_session_file_disappears(tmp_path) -> None:
    import json

    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    first = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-a", persist=True)
    first.append_message(UserMessage(role="user", content=[TextPart(type="text", text="keep me")], timestamp=1000.0))
    second = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project-b", persist=True)
    second.append_message(UserMessage(role="user", content=[TextPart(type="text", text="delete me")], timestamp=2000.0))
    second_file = second.get_session_file()
    assert second_file is not None
    SessionManager.refresh_index(tmp_path)

    second_file.unlink()
    summaries = SessionManager.list_indexed_summaries(tmp_path)
    raw_index = json.loads(SessionManager.index_file(tmp_path).read_text(encoding="utf-8"))

    assert [summary.session_id for summary in summaries] == [first.get_header().id]
    assert [item["session_id"] for item in raw_index["summaries"]] == [first.get_header().id]


def test_session_manager_rebuilds_nested_stale_indexes_during_all_index_query(tmp_path) -> None:
    import json

    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    root = SessionManager.new(session_dir=tmp_path, cwd="/tmp/root-project", persist=True)
    root.append_message(UserMessage(role="user", content=[TextPart(type="text", text="root")], timestamp=1000.0))
    nested_dir = tmp_path / "nested"
    nested = SessionManager.new(session_dir=nested_dir, cwd="/tmp/nested-project", persist=True)
    nested.append_message(UserMessage(role="user", content=[TextPart(type="text", text="nested")], timestamp=2000.0))
    nested_file = nested.get_session_file()
    assert nested_file is not None
    SessionManager.refresh_all_indexes(tmp_path)

    nested_file.unlink()
    summaries = SessionManager.list_all_indexed_summaries(tmp_path)
    nested_index = json.loads(SessionManager.index_file(nested_dir).read_text(encoding="utf-8"))

    assert [summary.session_id for summary in summaries] == [root.get_header().id]
    assert nested_index["summaries"] == []


def test_find_sessions_rejects_negative_limit(tmp_path) -> None:
    import pytest

    from loushang.coding.store import SessionManager, SessionQuery

    with pytest.raises(ValueError, match="limit"):
        SessionManager.find_sessions(tmp_path, SessionQuery(limit=-1))


def test_session_manager_open_can_override_session_dir_and_cwd(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    source_dir = tmp_path / "source"
    future_dir = tmp_path / "future"
    manager = SessionManager.new(session_dir=source_dir, cwd="/tmp/original", persist=True)
    manager.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="hello")],
            timestamp=0.0,
        )
    )

    opened = SessionManager.open(manager.get_session_file(), session_dir=future_dir, cwd_override="/tmp/current")

    assert opened.get_cwd() == "/tmp/current"
    assert opened.get_session_dir() == future_dir
    assert opened.get_session_file() == manager.get_session_file()
    assert opened.get_header().cwd == "/tmp/current"


def test_session_manager_open_recovers_invalid_empty_session_file(tmp_path) -> None:
    import json

    from loushang.coding.store import SessionManager

    session_file = tmp_path / "empty.jsonl"
    session_file.write_text("", encoding="utf-8")

    recovered = SessionManager.open(
        session_file,
        session_dir=tmp_path / "future",
        cwd_override="/tmp/current",
        persist=True,
    )
    reopened = SessionManager.open(session_file)
    lines = session_file.read_text(encoding="utf-8").splitlines()

    assert recovered.get_session_file() == session_file
    assert recovered.get_session_dir() == tmp_path / "future"
    assert recovered.get_cwd() == "/tmp/current"
    assert recovered.get_entries() == []
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "session"
    assert reopened.get_header().id == recovered.get_header().id
    assert reopened.get_cwd() == "/tmp/current"


def test_session_manager_open_recovers_invalid_header_session_file(tmp_path) -> None:
    import json

    from loushang.coding.store import SessionManager

    session_file = tmp_path / "broken.jsonl"
    session_file.write_text("not-json\n", encoding="utf-8")

    recovered = SessionManager.open(session_file, cwd_override="/tmp/current", persist=True)

    header = json.loads(session_file.read_text(encoding="utf-8").splitlines()[0])
    assert header["type"] == "session"
    assert header["cwd"] == "/tmp/current"
    assert recovered.get_header().id == header["id"]


def test_session_manager_open_recovers_missing_header_session_file(tmp_path) -> None:
    import json

    from loushang.coding.store import SessionManager

    session_file = tmp_path / "not-session.jsonl"
    session_file.write_text('{"type":"message","id":"e1","timestamp":"x"}\n', encoding="utf-8")

    recovered = SessionManager.open(session_file, cwd_override="/tmp/current", persist=True)

    lines = session_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "session"
    assert recovered.get_entries() == []


def test_session_manager_continue_recent_uses_latest_summary_or_creates_new(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    empty = SessionManager.continue_recent(session_dir=tmp_path / "empty", cwd="/tmp/project")
    assert empty.get_cwd() == "/tmp/project"
    assert empty.get_session_file() is not None

    older = SessionManager.new(session_dir=tmp_path, cwd="/tmp/old", persist=True)
    older.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="older")],
            timestamp=1000.0,
        )
    )
    newer = SessionManager.new(session_dir=tmp_path, cwd="/tmp/new", persist=True)
    newer.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="newer")],
            timestamp=2000.0,
        )
    )

    continued = SessionManager.continue_recent(session_dir=tmp_path, cwd="/tmp/current")

    assert continued.get_session_file() == newer.get_session_file()
    assert continued.get_cwd() == "/tmp/current"
    assert continued.get_header().cwd == "/tmp/current"


def test_session_manager_in_memory_and_fork_from(tmp_path) -> None:
    from loushang.ai.types import TextPart, UserMessage
    from loushang.coding.store import SessionManager

    memory = SessionManager.in_memory(cwd="/tmp/memory")
    assert memory.get_cwd() == "/tmp/memory"
    assert memory.get_session_file() is None
    assert memory.is_persisted() is False

    source = SessionManager.new(session_dir=tmp_path / "source", cwd="/tmp/source", persist=True)
    source.append_message(
        UserMessage(
            role="user",
            content=[TextPart(type="text", text="copy me")],
            timestamp=0.0,
        )
    )

    forked = SessionManager.fork_from(
        source.get_session_file(),
        target_cwd="/tmp/target",
        session_dir=tmp_path / "target",
    )

    assert forked.get_cwd() == "/tmp/target"
    assert forked.get_session_file() is not None
    assert forked.get_session_file().parent == tmp_path / "target"
    assert forked.get_header().parent_session == str(source.get_session_file())
    assert [entry.id for entry in forked.get_entries()] == [entry.id for entry in source.get_entries()]
