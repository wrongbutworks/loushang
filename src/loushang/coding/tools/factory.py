from __future__ import annotations

from dataclasses import replace
from typing import Any

from loushang.agent.types import AgentTool
from loushang.harness.tools.workspace.context import ToolContextProvider
from loushang.harness.tools.workspace.external_tools import (
    GitHubReleaseExternalToolDownloader,
)
from loushang.harness.tools.workspace.factory import (
    ALL_TOOL_NAMES,
    CORE_WORKSPACE_TOOL_NAMES,
    READ_ONLY_TOOL_NAMES,
    Tool,
    ToolDef,
    ToolName,
    ToolsOptions,
    allToolNames,
    coreWorkspaceToolNames,
    create_all_tool_definitions,
    create_all_tools,
    create_bash_tool,
    create_edit_tool,
    create_find_tool,
    create_grep_tool,
    create_ls_tool,
    create_read_only_tool_definitions,
    create_read_only_tools,
    create_read_tool,
    create_tool,
    create_write_tool,
    createAllToolDefinitions,
    createAllTools,
    createBashTool,
    createEditTool,
    createFindTool,
    createGrepTool,
    createLsTool,
    createReadOnlyToolDefinitions,
    createReadOnlyTools,
    createReadTool,
    createTool,
    createToolDefinition,
    createWriteTool,
    readOnlyToolNames,
)
from loushang.harness.tools.workspace.factory import (
    create_tool_definition as _create_tool_definition,
)
from loushang.harness.tools.workspace.types import ToolDefinition

CODING_TOOL_NAMES: tuple[ToolName, ...] = CORE_WORKSPACE_TOOL_NAMES
codingToolNames: set[ToolName] = set(coreWorkspaceToolNames)
_CODING_TOOL_TEXT: dict[ToolName, tuple[str, str]] = {
    "read": (
        "Read text files and images from the coding workspace. "
        "For large text files, use offset and limit to continue reading.",
        "- read: Read text files and images from the coding workspace.",
    ),
    "bash": (
        "Execute a shell command through the coding exec service.",
        "- bash: Execute shell commands. Prefer a single command string; use cwd for the working directory.",
    ),
    "edit": (
        "Apply exact text replacements to a file in the coding workspace.",
        "- edit: Apply exact text replacements to a file in the coding workspace.",
    ),
    "write": (
        "Write a text file in the coding workspace.",
        "- write: Write a text file in the coding workspace.",
    ),
    "grep": (
        "Search file contents in the coding workspace.",
        "- grep: Search file contents for patterns in the coding workspace.",
    ),
    "find": (
        "Find file paths in the coding workspace.",
        "- find: Find file paths by glob pattern in the coding workspace.",
    ),
    "ls": (
        "List directory entries in the coding workspace.",
        "- ls: List directory entries in the coding workspace.",
    ),
}


def create_tool_definition(
    tool_name: ToolName,
    *,
    options: ToolsOptions | None = None,
) -> ToolDefinition:
    if (
        tool_name in {"find", "grep"}
        and options is not None
        and options.external_tool_downloader is None
        and options.external_tool_policy != "never"
        and options.allow_external_tool_downloads
    ):
        options = replace(
            options,
            external_tool_downloader=GitHubReleaseExternalToolDownloader(),
        )
    definition = _create_tool_definition(tool_name, options=options)
    description, prompt_snippet = _CODING_TOOL_TEXT[tool_name]
    return replace(
        definition,
        description=description,
        prompt_snippet=prompt_snippet,
    )


def create_coding_tool_definitions(
    *, options: ToolsOptions | None = None
) -> list[ToolDefinition]:
    return [
        create_tool_definition(tool_name, options=options)
        for tool_name in CODING_TOOL_NAMES
    ]


def create_coding_tools(
    *,
    cwd: str | None = None,
    options: ToolsOptions | None = None,
    context_provider: ToolContextProvider | None = None,
    model: object | None = None,
) -> list[AgentTool[Any]]:
    return [
        create_tool(
            tool_name,
            cwd=cwd,
            options=options,
            context_provider=context_provider,
            model=model,
        )
        for tool_name in CODING_TOOL_NAMES
    ]


def createCodingToolDefinitions(
    cwd: str | None = None,
    options: ToolsOptions | None = None,
) -> list[ToolDefinition]:
    del cwd
    return create_coding_tool_definitions(options=options)


def createCodingTools(
    cwd: str | None = None,
    options: ToolsOptions | None = None,
) -> list[AgentTool[Any]]:
    return create_coding_tools(cwd=cwd, options=options)


__all__ = [
    "ALL_TOOL_NAMES",
    "CODING_TOOL_NAMES",
    "READ_ONLY_TOOL_NAMES",
    "Tool",
    "ToolDef",
    "ToolName",
    "ToolsOptions",
    "allToolNames",
    "codingToolNames",
    "create_all_tool_definitions",
    "create_all_tools",
    "create_bash_tool",
    "create_coding_tool_definitions",
    "create_coding_tools",
    "create_edit_tool",
    "create_find_tool",
    "create_grep_tool",
    "create_ls_tool",
    "create_read_only_tool_definitions",
    "create_read_only_tools",
    "create_read_tool",
    "create_tool",
    "create_tool_definition",
    "create_write_tool",
    "createAllToolDefinitions",
    "createAllTools",
    "createBashTool",
    "createCodingToolDefinitions",
    "createCodingTools",
    "createEditTool",
    "createFindTool",
    "createGrepTool",
    "createLsTool",
    "createReadOnlyToolDefinitions",
    "createReadOnlyTools",
    "createReadTool",
    "createTool",
    "createToolDefinition",
    "createWriteTool",
    "readOnlyToolNames",
]
