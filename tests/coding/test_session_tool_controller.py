from __future__ import annotations

import asyncio
from pathlib import Path

from loushang.agent import Agent
from loushang.agent.types import AgentToolResult
from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.loader import ResourceBundle
from loushang.coding.session.tool_controller import ToolController
from loushang.coding.store import SessionManager
from loushang.coding.tools import ToolContext, ToolDefinition, ToolRegistry, tool


async def _execute_noop(tool_call_id: str, params: dict[str, object], signal=None, on_update=None):
    del tool_call_id, params, signal, on_update
    return AgentToolResult(content=[], details={})


def _tool_definition(
    name: str,
    *,
    label: str | None = None,
    description: str | None = None,
    prompt_snippet: str | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        label=label or name.replace("_", " ").title(),
        description=description or f"{name} tool",
        parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        execute=_execute_noop,
        prompt_snippet=prompt_snippet,
    )


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


def test_tool_controller_routes_runtime_registration_through_contribution_resolver(
    tmp_path,
    monkeypatch,
) -> None:
    import loushang.coding.session.tool_controller as tool_controller
    from loushang.harness.tools.contribution import resolve_tool_contributions

    base_tool = _tool_definition("read", label="Read", description="Read files")
    runtime_tool = _tool_definition(
        "runtime_tool",
        label="Runtime Tool",
        description="Registered at runtime",
    )
    registry = ToolRegistry()
    registry.register_tool(base_tool, source_info={"source": "base"})
    runtime_source_info = {"source": "extension", "path": str(tmp_path / "extension.py")}
    calls: list[tuple[tuple[str, ...], object | None, dict[str, object], dict[str, object]]] = []

    def spy_resolver(contributions, **kwargs):
        contribution_tuple = tuple(contributions)
        runtime_contribution = contribution_tuple[-1]
        calls.append(
            (
                tuple(contribution.definition.name for contribution in contribution_tuple),
                runtime_contribution.source_info,
                dict(runtime_contribution.metadata),
                dict(kwargs),
            )
        )
        return resolve_tool_contributions(contribution_tuple, **kwargs)

    monkeypatch.setattr(tool_controller, "resolve_tool_contributions", spy_resolver, raising=False)
    controller = ToolController(
        agent=Agent(initial_state={"tools": []}),
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=registry,
        allowed_tool_names=None,
        initial_active_tool_names=[],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    definition = controller.register_runtime_tool(runtime_tool, source_info=runtime_source_info)

    assert definition.name == "runtime_tool"
    assert calls == [
        (
            ("read", "runtime_tool"),
            runtime_source_info,
            {
                "kind": "runtime_tool",
                "runtime_tool": "runtime_tool",
            },
            {"fail_on_errors": False},
        )
    ]
    assert [definition.name for definition in registry.list_definitions()] == ["read", "runtime_tool"]
    assert registry.get_source_info("runtime_tool") == runtime_source_info


def test_tool_controller_registers_selected_runtime_resolver_contribution(
    tmp_path,
    monkeypatch,
) -> None:
    import loushang.coding.session.tool_controller as tool_controller
    from loushang.harness.tools.contribution import (
        ToolContribution,
        ToolResolutionResult,
    )

    runtime_tool = _tool_definition(
        "runtime_tool",
        description="Original runtime contribution",
    )
    selected_tool = _tool_definition(
        "runtime_tool",
        description="Selected runtime contribution",
    )
    selected_source_info = {"source": "resolver"}

    def fake_resolver(contributions, **kwargs):
        del kwargs
        original_contribution = tuple(contributions)[-1]
        selected_contribution = ToolContribution(
            selected_tool,
            source_info=selected_source_info,
            metadata=original_contribution.metadata,
        )
        return ToolResolutionResult(
            contributions=(selected_contribution,),
            definitions=(selected_contribution.definition,),
        )

    monkeypatch.setattr(tool_controller, "resolve_tool_contributions", fake_resolver)
    registry = ToolRegistry()
    controller = ToolController(
        agent=Agent(initial_state={"tools": []}),
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=registry,
        allowed_tool_names=None,
        initial_active_tool_names=[],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    definition = controller.register_runtime_tool(runtime_tool, source_info={"source": "runtime"})

    assert definition.description == "Selected runtime contribution"
    assert registry.get_definition("runtime_tool").description == "Selected runtime contribution"
    assert registry.get_source_info("runtime_tool") == selected_source_info


def test_tool_controller_runtime_registration_preserves_duplicate_overwrite_behavior(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register_tool(
        _tool_definition("runtime_tool", description="Original runtime tool"),
        source_info={"source": "existing"},
    )
    controller = ToolController(
        agent=Agent(initial_state={"tools": []}),
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=registry,
        allowed_tool_names=None,
        initial_active_tool_names=[],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: None,
        get_diagnostics_service=lambda: None,
    )

    definition = controller.register_runtime_tool(
        _tool_definition("runtime_tool", description="Replacement runtime tool"),
        source_info={"source": "runtime"},
    )

    assert definition.description == "Replacement runtime tool"
    assert [definition.name for definition in registry.list_definitions()] == ["runtime_tool"]
    assert registry.get_definition("runtime_tool").description == "Replacement runtime tool"
    assert registry.get_source_info("runtime_tool") == {"source": "runtime"}


def test_tool_controller_runtime_registration_preserves_default_activation(tmp_path) -> None:
    registry = ToolRegistry()
    agent = Agent(initial_state={"system_prompt": "stale", "tools": []})
    controller = ToolController(
        agent=agent,
        session_manager=SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False),
        tool_registry=registry,
        allowed_tool_names=None,
        initial_active_tool_names=[],
        base_prompt="Base prompt.",
        get_resource_bundle=lambda: ResourceBundle(cwd=Path("/tmp/project"), prompt_fragments=[]),
        get_diagnostics_service=lambda: None,
        default_activate_new_tools=True,
    )

    controller.register_runtime_tool(
        _tool_definition(
            "runtime_tool",
            description="Runtime tool",
            prompt_snippet="- runtime_tool: run runtime behavior",
        )
    )

    assert controller.get_active_tool_names() == ["runtime_tool"]
    assert [tool.name for tool in agent.tools] == ["runtime_tool"]
    assert "- runtime_tool: run runtime behavior" in agent.system_prompt
