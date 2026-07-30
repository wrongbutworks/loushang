from __future__ import annotations

import asyncio
import json
from io import StringIO

from loushang.harness.host.rpc import RpcHost
from tests.coding.test_rpc_mode import (
    FakeRuntime,
    FakeSession,
    _assistant_message,
)


def _play_rpc_wire(
    runtime: FakeRuntime,
    *commands: dict[str, object],
) -> list[dict[str, object]]:
    stdin = StringIO(
        "\n".join(json.dumps(command) for command in commands) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await RpcHost(
            runtime=runtime,
            stdin=stdin,
            stdout=stdout,
        ).run()
        assert exit_code == 0

    asyncio.run(scenario())
    return [
        json.loads(line)
        for line in stdout.getvalue().splitlines()
        if line.strip()
    ]


def test_rpc_wire_playback_preserves_cross_group_success_golden() -> None:
    session = FakeSession(
        session_id="session-a",
        cwd="/tmp/project",
        messages=[_assistant_message("ready")],
    )
    session.command_entries = [
        {
            "name": "deploy",
            "description": "Deploy project",
            "source": "extension",
            "source_info": {"path": "/tmp/project/extensions/deploy.py"},
        }
    ]
    session.packages = [{"name": "core", "source": "builtin"}]

    assert _play_rpc_wire(
        FakeRuntime(session),
        {"id": "commands", "type": "get_commands"},
        {"id": "last", "type": "get_last_assistant_text"},
        {"id": "models", "type": "get_available_models"},
        {"id": "packages", "type": "get_packages"},
        {"id": "compact", "type": "compact"},
        {
            "id": "export",
            "type": "export_html",
            "outputPath": "/tmp/exported.html",
        },
    ) == [
        {
            "id": "commands",
            "type": "response",
            "command": "get_commands",
            "success": True,
            "data": {
                "commands": [
                    {
                        "name": "deploy",
                        "description": "Deploy project",
                        "source": "extension",
                        "sourceInfo": {
                            "path": "/tmp/project/extensions/deploy.py",
                            "source": "filesystem",
                            "scope": "project",
                            "origin": "top-level",
                            "baseDir": "/tmp/project/extensions",
                        },
                    }
                ]
            },
        },
        {
            "id": "last",
            "type": "response",
            "command": "get_last_assistant_text",
            "success": True,
            "data": {"text": "ready"},
        },
        {
            "id": "models",
            "type": "response",
            "command": "get_available_models",
            "success": True,
            "data": {"models": []},
        },
        {
            "id": "packages",
            "type": "response",
            "command": "get_packages",
            "success": True,
            "data": {"packages": [{"name": "core", "source": "builtin"}]},
        },
        {
            "id": "compact",
            "type": "response",
            "command": "compact",
            "success": True,
            "data": {
                "summary": "compacted",
                "firstKeptEntryId": "entry-1",
                "tokensBefore": 42,
                "details": {"preserved": 3},
            },
        },
        {
            "id": "export",
            "type": "response",
            "command": "export_html",
            "success": True,
            "data": {"path": "/tmp/exported.html"},
        },
    ]


def test_rpc_wire_playback_resolves_groups_against_rebound_session() -> None:
    initial = FakeSession(
        session_id="initial",
        cwd="/tmp/project",
        messages=[_assistant_message("old")],
    )
    replacement = FakeSession(
        session_id="replacement",
        cwd="/tmp/project",
        messages=[_assistant_message("new")],
    )
    replacement.command_entries = [
        {
            "name": "replacement-command",
            "source": "prompt",
            "source_info": {"path": "/tmp/project/prompts/replacement.md"},
        }
    ]
    runtime = FakeRuntime(initial)
    runtime.queue_next_session(replacement)

    assert _play_rpc_wire(
        runtime,
        {"id": "new", "type": "new_session"},
        {"id": "last", "type": "get_last_assistant_text"},
        {"id": "commands", "type": "get_commands"},
    ) == [
        {
            "id": "new",
            "type": "response",
            "command": "new_session",
            "success": True,
            "data": {"cancelled": False},
        },
        {
            "id": "last",
            "type": "response",
            "command": "get_last_assistant_text",
            "success": True,
            "data": {"text": "new"},
        },
        {
            "id": "commands",
            "type": "response",
            "command": "get_commands",
            "success": True,
            "data": {
                "commands": [
                    {
                        "name": "replacement-command",
                        "description": None,
                        "source": "prompt",
                        "sourceInfo": {
                            "path": "/tmp/project/prompts/replacement.md",
                            "source": "filesystem",
                            "scope": "project",
                            "origin": "top-level",
                            "baseDir": "/tmp/project/prompts",
                        },
                    }
                ]
            },
        },
    ]


def test_rpc_wire_playback_preserves_async_prompt_and_bash_golden() -> None:
    session = FakeSession(session_id="session-a", cwd="/tmp/project")

    assert _play_rpc_wire(
        FakeRuntime(session),
        {"id": "prompt", "type": "prompt", "message": "hello"},
        {"id": "bash", "type": "bash", "command": "printf ok"},
    ) == [
        {
            "id": "prompt",
            "type": "response",
            "command": "prompt",
            "success": True,
        },
        {
            "id": "bash",
            "type": "response",
            "command": "bash",
            "success": True,
            "data": {
                "output": "ok\n",
                "exitCode": 0,
                "cancelled": False,
                "truncated": False,
                "fullOutputPath": None,
            },
        },
    ]
    assert session.prompt_calls == [("hello", None)]
    assert session.wait_calls == 1
    assert session.bash_calls == [
        {
            "command": "printf ok",
            "cwd": None,
            "env": None,
            "timeout_seconds": None,
            "stdin": None,
        }
    ]


def test_rpc_wire_playback_preserves_validation_error_golden() -> None:
    session = FakeSession(session_id="session-a", cwd="/tmp/project")

    assert _play_rpc_wire(
        FakeRuntime(session),
        {
            "id": "prefix",
            "type": "get_command_completions",
            "prefix": 3,
        },
        {
            "id": "command",
            "type": "get_command_completions",
            "command": "",
        },
    ) == [
        {
            "id": "prefix",
            "type": "response",
            "command": "get_command_completions",
            "success": False,
            "error": "Command completion prefix must be a string.",
            "errorCode": "invalid_request",
            "errorInfo": {
                "code": "invalid_request",
                "message": "Command completion prefix must be a string.",
                "command": "get_command_completions",
            },
        },
        {
            "id": "command",
            "type": "response",
            "command": "get_command_completions",
            "success": False,
            "error": "Command completion command must be a non-empty string.",
            "errorCode": "invalid_request",
            "errorInfo": {
                "code": "invalid_request",
                "message": (
                    "Command completion command must be a non-empty string."
                ),
                "command": "get_command_completions",
            },
        },
    ]
