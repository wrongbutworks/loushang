from __future__ import annotations

import asyncio

from loushang.agent import Agent
from loushang.agent.types import AgentToolResult
from loushang.ai.types import TextPart
from loushang.coding.session.bash_controller import BashController
from loushang.coding.store import SessionManager
from loushang.harness.conversation import CommandExecutionRecord
from loushang.harness.workspace.exec import ExecOutputChunk


def test_bash_controller_executes_tool_forwards_output_and_records_context(
    tmp_path,
) -> None:
    manager = asyncio.run(
        SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
    )
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
