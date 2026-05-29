from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.agent import Agent
from loushang.agent.types import AgentToolResult
from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.loader import ResourceBundle
from loushang.coding.session.tool_controller import ToolController
from loushang.coding.store import SessionManager
from loushang.coding.tools import ToolDefinition, ToolRegistry, tool
from loushang.coding.tools import ToolContext


def test_tool_controller_materializes_active_registry_tools_and_rebuilds_prompt(tmp_path) -> None:
    @tool(prompt_snippet="Show the session cwd.")
    async def show_session_cwd(ctx: ToolContext) -> str:
        """Show the session cwd."""
        return ctx.cwd or ""

    registry = ToolRegistry()
    registry.register_tool(show_session_cwd)
    agent = Agent(initial_state={"system_prompt": "stale prompt", "tools": []})
    diagnostics = DiagnosticsService()

    controller = ToolController(
        agent=agent,
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=registry,
        allowed_tool_names=None,
        initial_active_tool_names=["show_session_cwd"],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: ResourceBundle(cwd=Path("/tmp/project"), prompt_fragments=["Repo rules"]),
        get_diagnostics_service=lambda: diagnostics,
    )
    controller.apply_active_tools(["show_session_cwd"])

    result = asyncio.run(agent.tools[0].execute("call-1", {}))

    assert controller.get_active_tool_names() == ["show_session_cwd"]
    assert result.content[0].text == "/tmp/project"
    assert "Base prompt." in agent.system_prompt
    assert "Repo rules" in agent.system_prompt
    assert "Available tools:\n- show_session_cwd:" in agent.system_prompt


def test_tool_controller_filters_allowed_visible_and_active_tools(tmp_path) -> None:
    async def _execute(tool_call_id: str, params: dict[str, object], signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[], details={})

    registry = ToolRegistry()
    registry.register_tool(
        ToolDefinition(
            name="read",
            label="Read",
            description="Read files",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            execute=_execute,
        )
    )
    registry.register_tool(
        ToolDefinition(
            name="bash",
            label="Bash",
            description="Run commands",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            execute=_execute,
        )
    )
    controller = ToolController(
        agent=Agent(initial_state={"tools": []}),
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=registry,
        allowed_tool_names={"read"},
        initial_active_tool_names=["bash", "read", "missing"],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    controller.apply_active_tools(["bash", "read", "missing"])

    assert controller.get_active_tool_names() == ["read"]
    assert [definition.name for definition in controller.get_all_tools()] == ["read"]
    assert controller.get_tool_definition("bash") is None
    assert [tool.name for tool in controller.agent.tools] == ["read"]


def test_tool_controller_reads_runtime_tools_when_registry_is_absent(tmp_path) -> None:
    class RuntimeTool:
        name = "runtime_tool"
        label = "Runtime Tool"
        description = "runtime tool"
        parameters = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        prepare_arguments = None
        execution_mode = "parallel"

        async def execute(self, tool_call_id: str, params: dict[str, object], signal=None, on_update=None):
            del tool_call_id, params, signal, on_update
            return AgentToolResult(content=[], details={})

    agent = Agent(initial_state={"tools": [RuntimeTool()]})
    controller = ToolController(
        agent=agent,
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=None,
        allowed_tool_names=None,
        initial_active_tool_names=["runtime_tool"],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    assert controller.get_active_tool_names() == ["runtime_tool"]
    assert [definition.name for definition in controller.get_all_tools()] == ["runtime_tool"]
    assert controller.get_tool_definition("runtime_tool").name == "runtime_tool"
