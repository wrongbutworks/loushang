from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.agent.types import AgentToolResult
from loushang.ai.types import TextPart
from loushang.coding.exec import ExecOutputChunk
from loushang.coding.session.bash_controller import BashController
from loushang.coding.store import SessionManager
from loushang.harness.conversation import CommandExecutionRecord


def test_bash_controller_executes_tool_forwards_output_and_records_context(tmp_path) -> None:
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    agent = Agent()
    chunks: list[ExecOutputChunk] = []
    executed: list[tuple[str, dict[str, object]]] = []

    class BashTool:
        async def execute(self, tool_call_id, params, signal=None, on_update=None):
            del signal
            executed.append((tool_call_id, params))
            if on_update is not None:
                await on_update(
                    AgentToolResult(
                        content=[TextPart(type="text", text="streamed\n")],
                        details={"stream": "stdout"},
                    )
                )
            return AgentToolResult(
                content=[TextPart(type="text", text="final\n")],
                details={"exit_code": 0},
            )

    class ToolRegistry:
        def get_definition(self, name: str):
            assert name == "bash"
            return BashTool()

    async def _on_output(chunk: ExecOutputChunk) -> None:
        chunks.append(chunk)

    controller = BashController(
        agent=agent,
        session_manager=manager,
        get_extension_runner=lambda: None,
        get_tool_registry=lambda: ToolRegistry(),
    )

    result = asyncio.run(controller.execute_bash("printf hi", on_output=_on_output))

    assert result == {
        "output": "final\n",
        "exit_code": 0,
        "cancelled": False,
        "truncated": False,
        "full_output_path": None,
    }
    assert executed[0][1]["command"] == ["/bin/bash", "-lc", "printf hi"]
    assert chunks == [ExecOutputChunk(stream="stdout", text="streamed\n")]
    assert controller.is_running is False
    assert agent.state.messages[-1].role == "user"
    command = manager.get_entries()[-1].payload
    assert isinstance(command, CommandExecutionRecord)
    assert command.command == "printf hi"


def test_bash_controller_execute_pi_style_translates_options_and_result_aliases(tmp_path) -> None:
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    agent = Agent()
    chunks: list[str] = []
    executed: list[dict[str, object]] = []

    class BashTool:
        async def execute(self, tool_call_id, params, signal=None, on_update=None):
            del tool_call_id, signal
            executed.append(params)
            if on_update is not None:
                await on_update(
                    AgentToolResult(
                        content=[TextPart(type="text", text="streamed\n")],
                        details={"stream": "stdout"},
                    )
                )
            return AgentToolResult(
                content=[TextPart(type="text", text="final\n")],
                details={"exit_code": 0, "stdout_artifact_path": "/tmp/out.log"},
            )

    class ToolRegistry:
        def get_definition(self, name: str):
            assert name == "bash"
            return BashTool()

    controller = BashController(
        agent=agent,
        session_manager=manager,
        get_extension_runner=lambda: None,
        get_tool_registry=lambda: ToolRegistry(),
    )

    result = asyncio.run(
        controller.execute_pi_style(
            "cat",
            on_chunk=chunks.append,
            options={
                "cwd": "/tmp/alt",
                "timeoutSeconds": 3,
                "stdin": "input",
                "excludeFromContext": True,
            },
        )
    )

    assert result["exitCode"] == 0
    assert result["fullOutputPath"] == "/tmp/out.log"
    assert executed == [
        {
            "command": ["/bin/bash", "-lc", "cat"],
            "cwd": "/tmp/alt",
            "timeout_seconds": 3.0,
            "stdin": "input",
        }
    ]
    assert chunks == ["streamed\n"]
    assert agent.state.messages == []
    command = manager.get_entries()[-1].payload
    assert isinstance(command, CommandExecutionRecord)
    assert command.exclude_from_context is True


def test_bash_controller_record_pi_style_result_normalizes_aliases(tmp_path) -> None:
    manager = SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    agent = Agent()
    controller = BashController(
        agent=agent,
        session_manager=manager,
        get_extension_runner=lambda: None,
        get_tool_registry=lambda: None,
    )

    controller.record_pi_style_result(
        "echo hi",
        {"output": "hi\n", "exitCode": 0, "fullOutputPath": "/tmp/out.log"},
        {"excludeFromContext": True},
    )

    assert agent.state.messages == []
    command = manager.get_entries()[-1].payload
    assert isinstance(command, CommandExecutionRecord)
    assert command.command == "echo hi"
    assert command.output == "hi\n"
    assert command.exit_code == 0
    assert command.full_output_path == "/tmp/out.log"
    assert command.exclude_from_context is True
