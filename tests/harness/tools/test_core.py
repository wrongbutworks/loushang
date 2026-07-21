from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict

import pytest


class SearchArgs(TypedDict):
    pattern: str
    path: str
    ignore_case: NotRequired[bool]


@dataclass
class ReadArgs:
    path: str
    limit: int | None = None


def search(args: SearchArgs) -> None:
    del args


def read(args: ReadArgs) -> None:
    del args


def test_tool_definition_validates_prompt_guidelines_sequence() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.harness.tools.core import ToolDefinition

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[], details={})

    definition = ToolDefinition(
        name="demo",
        label="Demo",
        description="demo",
        parameters={"type": "object", "properties": {}, "required": []},
        execute=execute,
        prompt_guidelines=["one", "two"],
    )

    assert definition.prompt_guidelines == ("one", "two")

    with pytest.raises(TypeError, match="prompt_guidelines must be a sequence"):
        ToolDefinition(
            name="bad",
            label="Bad",
            description="bad",
            parameters={"type": "object", "properties": {}, "required": []},
            execute=execute,
            prompt_guidelines="bad",  # type: ignore[arg-type]
        )


def test_project_tool_definition_uses_neutral_source_info() -> None:
    from pathlib import Path

    from loushang.harness.tools.core import ToolDefinition, project_tool_definition

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return None

    definition = ToolDefinition(
        name="read",
        label="Read",
        description="Read files",
        parameters={"type": "object"},
        execute=execute,
    )

    assert project_tool_definition(
        definition, builtin_names=frozenset({"read"})
    )["sourceInfo"] == {
        "path": "<builtin:read>",
        "source": "builtin",
        "scope": "temporary",
        "origin": "top-level",
        "baseDir": None,
    }
    assert project_tool_definition(
        definition,
        type("Source", (), {"path": Path("tools.py"), "source": "filesystem"})(),
    )["sourceInfo"]["path"] == "tools.py"


def test_tool_decorator_attaches_metadata_without_normalizing_returns() -> None:
    from loushang.harness.tools.core import DecoratedToolSpec, tool

    @tool(name="hello", label="Hello", description="Say hello")
    async def greet(name: str) -> str:
        return f"hello {name}"

    spec = getattr(greet, "__loushang_tool_spec__")

    assert isinstance(spec, DecoratedToolSpec)
    assert spec.name == "hello"
    assert spec.label == "Hello"
    assert spec.description == "Say hello"
    assert spec.fn is greet


def test_schema_inference_handles_typeddict_and_dataclass() -> None:
    from loushang.harness.tools.core import infer_schema_from_signature

    search_schema = infer_schema_from_signature(search)
    read_schema = infer_schema_from_signature(read)

    assert search_schema["properties"]["args"]["properties"]["pattern"]["type"] == "string"
    assert "ignore_case" not in search_schema["properties"]["args"]["required"]
    assert read_schema["properties"]["args"]["properties"]["limit"]["anyOf"] == [
        {"type": "integer"},
        {"type": "null"},
    ]


def test_registry_accepts_neutral_definitions_and_preserves_order_and_source_info() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.harness.tools.core import ToolDefinition, ToolRegistry

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[], details={})

    first = ToolDefinition(
        name="first",
        label="First",
        description="first",
        parameters={"type": "object", "properties": {}, "required": []},
        execute=execute,
    )
    second = ToolDefinition(
        name="second",
        label="Second",
        description="second",
        parameters={"type": "object", "properties": {}, "required": []},
        execute=execute,
    )

    registry = ToolRegistry()
    registry.register_tool(first, source_info={"source": "test"})
    registry.register_tool(second, enabled=False)

    assert [definition.name for definition in registry.list_definitions()] == ["first", "second"]
    assert [definition.name for definition in registry.list_enabled_definitions()] == ["first"]
    assert registry.get_source_info("first") == {"source": "test"}

    registry.enable_tool("second")
    registry.disable_tool("first")

    assert [definition.name for definition in registry.list_enabled_definitions()] == ["second"]


def test_registry_rejects_decorated_plain_return_tools() -> None:
    from loushang.harness.tools.core import ToolRegistry, tool

    @tool()
    async def greet(name: str) -> str:
        return f"hello {name}"

    registry = ToolRegistry()

    with pytest.raises(TypeError, match="pre-normalized ToolDefinition"):
        registry.register_tool(greet)


def test_tools_core_does_not_export_pi_style_wrapper_aliases() -> None:
    import loushang.harness.tools.core as core

    assert not hasattr(core, "wrapToolDefinition")
    assert not hasattr(core, "wrapToolDefinitions")
    assert not hasattr(core, "createToolDefinitionFromAgentTool")


def test_wrap_tool_definition_uses_neutral_schema_and_executes() -> None:
    import asyncio

    from loushang.agent.types import AgentToolResult
    from loushang.harness.tools.core import ToolDefinition, wrap_tool_definition

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del signal, on_update
        return AgentToolResult(content=[], details={"tool_call_id": tool_call_id, "params": params})

    definition = ToolDefinition(
        name="demo",
        label="Demo",
        description="demo",
        parameters={"type": "object", "properties": {"value": {"type": "string"}}},
        provider_parameters={"type": "object", "properties": {"provider": {"type": "string"}}},
        execute=execute,
    )
    runtime_tool = wrap_tool_definition(definition)

    result = asyncio.run(runtime_tool.execute("call-1", {"value": "x"}))

    assert runtime_tool.name == "demo"
    assert runtime_tool.parameters == definition.parameters
    assert result.details == {"tool_call_id": "call-1", "params": {"value": "x"}}
