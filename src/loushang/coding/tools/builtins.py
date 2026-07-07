from __future__ import annotations

from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.exec import ExecService
from loushang.coding.policy import ApprovalResolver, PolicyEngine
from loushang.harness.tools.contribution import (
    ToolContribution,
    ToolPackDefinition,
    resolve_tool_contributions,
)

from .external_tools import (
    ExternalToolDownloader,
    ExternalToolPolicy,
    ExternalToolResolver,
)
from .factory import ToolsOptions, create_tool_definition
from .operations import ToolOperations
from .registry import ToolRegistry

BUILTIN_TOOL_NAMES = ("bash", "read", "ls", "find", "grep", "write", "edit")
BUILTIN_TOOL_PACK = ToolPackDefinition(name="coding.builtin", tools=BUILTIN_TOOL_NAMES)


def register_builtin_tools(
    registry: ToolRegistry,
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
) -> ToolRegistry:
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
        ToolContribution(create_tool_definition(tool_name, options=options))
        for tool_name in BUILTIN_TOOL_NAMES
    )
    result = resolve_tool_contributions(
        contributions,
        packs=(BUILTIN_TOOL_PACK,),
        include_packs=(BUILTIN_TOOL_PACK.name,),
    )
    for definition in result.definitions:
        registry.register_tool(definition)
    return registry
