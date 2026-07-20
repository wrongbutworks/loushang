"""Coding's selected workspace-tool pack.

Concrete workspace tools, their protocols, and their render/runtime helpers are
owned by :mod:`loushang.harness.tools.workspace`.  This module only describes
how the Coding product selects and configures that reusable capability.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from loushang.agent.types import AgentTool
from loushang.coding.policy import ApprovalResolver, PolicyEngine
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.tools.contribution import (
    ToolContribution,
    ToolPackDefinition,
    resolve_tool_contributions,
)
from loushang.harness.tools.core import ToolDefinition
from loushang.harness.tools.workspace.context import ToolContextProvider
from loushang.harness.tools.workspace.external_tools import (
    ExternalToolDownloader,
    ExternalToolPolicy,
    ExternalToolResolver,
    GitHubReleaseExternalToolDownloader,
)
from loushang.harness.tools.workspace.factory import (
    CORE_WORKSPACE_TOOL_NAMES,
    ToolName,
    ToolsOptions,
    create_tool,
)
from loushang.harness.tools.workspace.factory import (
    create_tool_definition as create_workspace_tool_definition,
)
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.harness.workspace.exec import ExecService
from loushang.harness.workspace.operations import ToolOperations

CODING_TOOL_NAMES: tuple[ToolName, ...] = CORE_WORKSPACE_TOOL_NAMES
CODING_BUILTIN_TOOL_NAMES: tuple[ToolName, ...] = (
    "bash",
    "read",
    "ls",
    "find",
    "grep",
    "write",
    "edit",
)
CODING_BUILTIN_TOOL_PACK = ToolPackDefinition(
    name="coding.builtin",
    tools=CODING_BUILTIN_TOOL_NAMES,
)

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


def create_coding_tool_definition(
    tool_name: ToolName,
    *,
    options: ToolsOptions | None = None,
) -> ToolDefinition:
    """Create a workspace definition with Coding's copy and download default."""
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
    definition = create_workspace_tool_definition(tool_name, options=options)
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
        create_coding_tool_definition(tool_name, options=options)
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


def register_coding_builtin_tools(
    registry: WorkspaceToolRegistry,
    *,
    policy_engine: PolicyEngine | None = None,
    approval_resolver: ApprovalResolver | None = None,
    exec_service: ExecService | None = None,
    diagnostics_service: DiagnosticsService | None = None,
    operations: ToolOperations | None = None,
    external_tool_resolver: ExternalToolResolver | None = None,
    external_tool_downloader: ExternalToolDownloader | None = None,
    external_tool_policy: ExternalToolPolicy | None = None,
    allow_external_tool_downloads: bool = False,
    require_external_tools: bool = False,
) -> WorkspaceToolRegistry:
    options = ToolsOptions(
        policy_engine=policy_engine,
        approval_resolver=approval_resolver,
        exec_service=exec_service or ExecService(),
        diagnostics_service=diagnostics_service,
        operations=operations,
        external_tool_resolver=external_tool_resolver,
        external_tool_downloader=external_tool_downloader,
        external_tool_policy=external_tool_policy,
        allow_external_tool_downloads=allow_external_tool_downloads,
        require_external_tools=require_external_tools,
    )
    contributions = tuple(
        ToolContribution(create_coding_tool_definition(tool_name, options=options))
        for tool_name in CODING_BUILTIN_TOOL_NAMES
    )
    result = resolve_tool_contributions(
        contributions,
        packs=(CODING_BUILTIN_TOOL_PACK,),
        include_packs=(CODING_BUILTIN_TOOL_PACK.name,),
    )
    for definition in result.definitions:
        registry.register_tool(definition)
    return registry


__all__ = [
    "CODING_BUILTIN_TOOL_NAMES",
    "CODING_BUILTIN_TOOL_PACK",
    "CODING_TOOL_NAMES",
    "create_coding_tool_definition",
    "create_coding_tool_definitions",
    "create_coding_tools",
    "register_coding_builtin_tools",
]
