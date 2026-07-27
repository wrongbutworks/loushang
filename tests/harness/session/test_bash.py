from __future__ import annotations

import asyncio

from loushang.agent.types import AgentToolResult
from loushang.ai.types import Context, TextPart
from loushang.harness.conversation import CommandExecutionRecord
from loushang.harness.session import BashExecutionPorts, BashExecutionRuntime
from loushang.harness.workspace.exec import ExecOutputChunk


def test_bash_runtime_executes_streams_and_records_context(tmp_path) -> None:
    del tmp_path

    class Transcript:
        def __init__(self) -> None:
            self.entries: list[object] = []

        def get_cwd(self) -> str:
            return "/tmp/project"

        async def append_message(self, record: object) -> None:
            self.entries.append(record)

        def build_session_context(self) -> Context:
            return Context(messages=[])

    transcript = Transcript()
    chunks: list[ExecOutputChunk] = []
    executed: list[tuple[str, dict[str, object]]] = []
    refreshes: list[bool] = []

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

    def refresh_context() -> None:
        refreshes.append(True)

    async def on_output(chunk: ExecOutputChunk) -> None:
        chunks.append(chunk)

    runtime = BashExecutionRuntime(
        BashExecutionPorts(
            get_cwd=transcript.get_cwd,
            get_definition=lambda: ToolRegistry().get_definition("bash"),
            create_call_id=lambda: "bash-test-1",
            append_record=transcript.append_message,
            refresh_context=refresh_context,
        )
    )
    result = asyncio.run(runtime.execute("printf hi", on_output=on_output))

    assert result == {
        "output": "final\n",
        "exit_code": 0,
        "cancelled": False,
        "truncated": False,
        "full_output_path": None,
    }
    assert executed[0][1]["command"] == ["/bin/bash", "-lc", "printf hi"]
    assert chunks == [ExecOutputChunk(stream="stdout", text="streamed\n")]
    assert runtime.is_running is False
    assert refreshes == [True]
    command = transcript.entries[-1]
    assert isinstance(command, CommandExecutionRecord)
    assert command.command == "printf hi"


def test_bash_runtime_injects_session_owned_operations() -> None:
    selected_operations = object()
    executed: list[dict[str, object]] = []

    async def append_record(record: object) -> None:
        del record

    class BashTool:
        async def execute(self, tool_call_id, params, signal=None, on_update=None):
            del tool_call_id, signal, on_update
            executed.append(params)
            return AgentToolResult(
                content=[TextPart(type="text", text="ok\n")],
                details={"exit_code": 0},
            )

    runtime = BashExecutionRuntime(
        BashExecutionPorts(
            get_cwd=lambda: "/tmp/project",
            get_definition=lambda: BashTool(),
            create_call_id=lambda: "bash-session-1",
            append_record=append_record,
            refresh_context=lambda: None,
            operations=selected_operations,
        )
    )

    asyncio.run(runtime.execute("true"))

    assert executed[0]["__operations"] is selected_operations
