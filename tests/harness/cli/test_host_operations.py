from __future__ import annotations

import asyncio
import json
from io import StringIO
from types import SimpleNamespace

from loushang.harness.cli import (
    CommandExecutionRequest,
    SessionListingOperationRequest,
    run_command_operation,
    run_session_listing_operation,
)


class _Runtime:
    def list_session_summaries(self) -> list[object]:
        return [
            "invalid",
            SimpleNamespace(
                session_id="session-1",
                cwd="/workspace",
                session_file=None,
                parent_session=None,
                leaf_id=None,
                metadata=SimpleNamespace(
                    created_at="2026-07-01T00:00:00Z",
                    updated_at="2026-07-02T00:00:00Z",
                    name="Example",
                ),
            ),
        ]


class _Session:
    async def execute_command_async(self, name: str, args: str) -> object:
        return SimpleNamespace(result={"name": name, "args": args})


def test_session_listing_operation_owns_query_validation_and_projection(
    monkeypatch,
) -> None:
    from loushang.harness.cli import host_operations

    original = host_operations.try_project_session_record
    monkeypatch.setattr(
        host_operations,
        "try_project_session_record",
        lambda record: None if record == "invalid" else original(record),
    )
    stdout = StringIO()
    stderr = StringIO()

    result = run_session_listing_operation(
        _Runtime(),
        SessionListingOperationRequest(output_format="json"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert [item["session_id"] for item in json.loads(stdout.getvalue())] == [
        "session-1"
    ]
    assert stderr.getvalue() == ""


def test_session_listing_operation_projects_invalid_limit_to_cli_error() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = run_session_listing_operation(
        _Runtime(),
        SessionListingOperationRequest(limit=-1),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Error: Session query limit must be non-negative\n"


def test_command_operation_writes_standard_result_envelope() -> None:
    stdout = StringIO()
    stderr = StringIO()

    result = asyncio.run(
        run_command_operation(
            _Session(),
            CommandExecutionRequest(
                command="/deploy",
                args="now",
                result_format="json",
            ),
            stdout=stdout,
            stderr=stderr,
        )
    )

    assert result == 0
    assert json.loads(stdout.getvalue()) == {
        "command": "deploy",
        "args": "now",
        "result": {"name": "deploy", "args": "now"},
    }
    assert stderr.getvalue() == ""
