from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path

import pytest

from loushang.harness.environment import HostEnvironment, LocalHostEnvironmentProbe
from loushang.harness.policy_engine import PolicyEngine
from loushang.harness.tools.workspace import ToolContext
from loushang.harness.tools.workspace.shell import create_shell_tool_definition
from loushang.harness.tools.workspace.wrapper import wrap_tool_definition
from loushang.harness.workspace.exec import ExecResult
from loushang.harness.workspace.shell import ResolvedShell


def _windows() -> HostEnvironment:
    return HostEnvironment(
        os_family="windows",
        platform_name="win32",
        architecture="amd64",
    )


class _ResolvedPowerShell:
    def resolve(self, selection=None) -> ResolvedShell:
        del selection
        return ResolvedShell(
            kind="powershell",
            executable=(
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
            ),
            flavor="windows-powershell",
            target_id="windows-local",
            target_os_family="windows",
            source="system",
            version="5.1",
            edition="Desktop",
        )


class _RecordingOperations:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def execute(self, request, *, signal=None, on_update=None):
        del signal, on_update
        self.requests.append(request)
        return ExecResult(exit_code=0, stdout="ok\n")


class _RecordingPolicy:
    def __init__(self) -> None:
        self.subjects: list[object] = []
        self._engine = PolicyEngine()

    def evaluate(self, subject):
        self.subjects.append(subject)
        return self._engine.evaluate(subject)


def _resolver_factory(environment, environ, cwd):
    del environment, environ, cwd
    return _ResolvedPowerShell()


def _context(cwd: Path):
    return lambda *, tool_call_id: ToolContext(
        tool_call_id=tool_call_id,
        cwd=str(cwd),
    )


def test_windows_shell_tool_authorizes_plaintext_and_executes_encoded_transport(
    tmp_path: Path,
) -> None:
    operations = _RecordingOperations()
    policy = _RecordingPolicy()
    definition = create_shell_tool_definition(
        operations=operations,
        environment=_windows(),
        resolver_factory=_resolver_factory,
    )
    tool = wrap_tool_definition(
        definition,
        context_provider=_context(tmp_path),
        policy_evaluator=policy,
    )

    result = asyncio.run(tool.execute("shell-1", {"command": "Get-Location"}))

    assert result.content[0].text == "ok\n"
    request = operations.requests[0]
    assert request.command[:5] == (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
    )
    decoded = base64.b64decode(request.command[-1]).decode("utf-16le")
    assert "Get-Location" in decoded
    assert request.cwd == str(tmp_path)

    subject = policy.subjects[0]
    assert subject.tool_name == "shell"
    assert subject.capability_id == "workspace.command"
    assert subject.command.shell_payload == "Get-Location"
    assert subject.command.dialect == "powershell"
    assert subject.command.shell_flavor == "windows-powershell"
    assert subject.arguments["resolved_shell"] == {
        "executable": (
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        ),
        "flavor": "windows-powershell",
        "kind": "powershell",
        "source": "system",
        "target_id": "windows-local",
        "transport": "encoded-command",
    }


def test_windows_shell_tool_fails_closed_before_execution_for_unknown_script(
    tmp_path: Path,
) -> None:
    from loushang.harness.tools.workspace import PolicyEnforcementError

    operations = _RecordingOperations()
    tool = wrap_tool_definition(
        create_shell_tool_definition(
            operations=operations,
            environment=_windows(),
            resolver_factory=_resolver_factory,
        ),
        context_provider=_context(tmp_path),
        policy_evaluator=PolicyEngine(),
    )

    with pytest.raises(PolicyEnforcementError) as raised:
        asyncio.run(tool.execute("shell-2", {"command": "Write-Output hello"}))

    assert raised.value.tool_result_details["policy_code"] == (
        "unclassified_powershell_command"
    )
    assert operations.requests == []


def test_windows_shell_tool_schema_and_runtime_reject_argv_input() -> None:
    definition = create_shell_tool_definition(
        environment=_windows(),
        resolver_factory=_resolver_factory,
    )

    assert definition.parameters["properties"]["command"] == {"type": "string"}
    tool = wrap_tool_definition(definition, policy_evaluator=PolicyEngine())
    with pytest.raises(TypeError, match="command must be a non-empty string"):
        asyncio.run(tool.execute("shell-3", {"command": ["cmd.exe", "/c", "dir"]}))


def test_windows_shell_tool_audit_records_safe_resolution_metadata(
    tmp_path: Path,
) -> None:
    from loushang.harness.tools.workspace import ToolContext

    events: list[dict[str, object]] = []
    operations = _RecordingOperations()
    tool = wrap_tool_definition(
        create_shell_tool_definition(
            operations=operations,
            environment=_windows(),
            resolver_factory=_resolver_factory,
        ),
        context_provider=lambda *, tool_call_id: ToolContext(
            tool_call_id=tool_call_id,
            cwd=str(tmp_path),
            event_sink=events.append,
        ),
        policy_evaluator=PolicyEngine(),
    )

    asyncio.run(tool.execute("shell-audit", {"command": "Get-Location"}))

    assert events[0]["policy_capability_id"] == "workspace.command"
    assert events[0]["shell_summary"] == {
        "kind": "powershell",
        "flavor": "windows-powershell",
        "source": "system",
        "target_id": "windows-local",
        "transport": "encoded-command",
    }
    assert "executable" not in events[0]["shell_summary"]


@pytest.mark.skipif(os.name != "nt", reason="requires a native Windows host")
def test_native_windows_shell_tool_runs_without_bash_installation(
    tmp_path: Path,
) -> None:
    tool = wrap_tool_definition(
        create_shell_tool_definition(
            environment=LocalHostEnvironmentProbe().detect(),
        ),
        context_provider=_context(tmp_path),
        policy_evaluator=PolicyEngine(),
    )

    result = asyncio.run(tool.execute("shell-native", {"command": "Get-Location"}))

    assert result.details["exit_code"] == 0
    assert result.content[0].text.strip()
