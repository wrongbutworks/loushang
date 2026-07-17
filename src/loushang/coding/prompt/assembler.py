from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from loushang.agent.types import AgentTool
from loushang.coding.prompt.types import PromptAssembly
from loushang.harness.capabilities.prompt import (
    PromptSection,
    PromptSectionComposer,
)
from loushang.harness.resources.activation import ResourceActivation
from loushang.harness.resources.types import ResourceBundle
from loushang.harness.tools.core import ToolDefinition

DEFAULT_SYSTEM_PROMPT = """\
You are an expert coding assistant operating inside loushang, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.

Guidelines:
- Be concise in your responses
- Show file paths clearly when working with files
- 首次探索工具调用前，必须先用一句话说明本轮要验证什么；不要直接开始扫描。
- 连续执行 3 次探索工具调用后，必须先汇总已确认信息，再决定是否继续。
- 避免无明确目标地批量列目录、搜索和读取文件；证据足够时停止探索并回答。
- 进度说明只在目标变化、关键证据、阶段切换或需用户决策时发送，保持简短。
- 多步骤任务阶段结束时说明结果、验证和下一步或阻塞。
- Prefer specialized tools over bash for file exploration when available
- Always read files completely before editing
- Follow project-specific instructions in <project_context> when present
"""


def _build_tool_prompt_from_tools(tools: list[AgentTool[Any]] | None) -> str:
    if not tools:
        return ""

    tool_lines = [
        f"- {tool.name}: {tool.description.strip()}"
        for tool in tools
        if isinstance(tool.description, str) and tool.description.strip()
    ]
    if not tool_lines:
        return ""
    return "Available tools:\n" + "\n".join(tool_lines)


def _build_tool_prompt_from_definitions(
    tool_definitions: list[ToolDefinition] | None,
) -> str:
    if not tool_definitions:
        return ""

    tool_lines: list[str] = []
    for definition in tool_definitions:
        snippet = _format_tool_prompt_snippet(definition)
        if not snippet:
            continue
        tool_lines.append(snippet)
        tool_lines.extend(_format_tool_prompt_guidelines(definition.prompt_guidelines))
    if not tool_lines:
        return ""
    return "Available tools:\n" + "\n".join(tool_lines)


def _format_tool_prompt_snippet(definition: ToolDefinition) -> str:
    snippet = (
        definition.prompt_snippet.strip()
        if isinstance(definition.prompt_snippet, str)
        else ""
    )
    if not snippet:
        return ""
    if snippet.startswith("-"):
        return snippet
    return f"- {definition.name}: {snippet}"


def _format_tool_prompt_guidelines(guidelines: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for guideline in guidelines:
        cleaned = guideline.strip()
        if not cleaned:
            continue
        lines.append(cleaned if cleaned.startswith("-") else f"- {cleaned}")
    return lines


def _build_skill_prompt(resource_activation: ResourceActivation) -> str:
    visible_skills = resource_activation.model_visible_skills()
    if not visible_skills:
        return ""
    lines = [
        "The following skills provide specialized instructions for specific tasks.",
        "Use the read tool to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory and use that absolute path in tool commands.",
        "",
        "<available_skills>",
    ]
    for skill in visible_skills:
        description = skill.description
        if not isinstance(description, str):
            continue
        lines.extend(
            [
                "  <skill>",
                f"    <name>{escape(skill.name)}</name>",
                f"    <description>{escape(description.strip())}</description>",
                f"    <location>{escape(skill.source_path.as_posix())}</location>",
                "  </skill>",
            ]
        )
    lines.append("</available_skills>")
    return "\n".join(lines)


def _build_project_context_prompt(resource_activation: ResourceActivation) -> str:
    descriptors = resource_activation.context_prompts()
    if not descriptors:
        return ""
    lines = [
        "# Project Context",
        "",
        "Project-specific instructions and guidelines:",
        "",
    ]
    for index, descriptor in enumerate(descriptors):
        if index:
            lines.append("")
        lines.extend(
            [
                f"## {descriptor.source_path.as_posix()}",
                "",
                descriptor.text.strip(),
            ]
        )
    return "\n".join(lines)


def _iter_non_context_prompt_fragments(
    resource_activation: ResourceActivation,
) -> list[str]:
    return list(resource_activation.prompt_fragments())


def _build_runtime_footer(resource_bundle: ResourceBundle | None) -> str:
    if resource_bundle is None:
        return ""
    cwd = resource_bundle.cwd.as_posix().replace("\\", "/")
    return f"Current date: {date.today().isoformat()}\nCurrent working directory: {cwd}"


def assemble_prompt(
    *,
    base_prompt: str | None = None,
    resource_bundle: ResourceBundle | None = None,
    tool_definitions: list[ToolDefinition] | None = None,
    tools: list[AgentTool[Any]] | None = None,
    tool_prompt: str | None = None,
    resource_activation: ResourceActivation | None = None,
    prompt_section_composer: PromptSectionComposer | None = None,
) -> PromptAssembly:
    sections: list[PromptSection] = []
    resource_fragments: list[str] = []
    effective_base = (
        base_prompt
        if isinstance(base_prompt, str) and base_prompt.strip()
        else DEFAULT_SYSTEM_PROMPT
    )
    sections.append(PromptSection("base", effective_base, kind="base"))
    activation = resource_activation or ResourceActivation(resource_bundle)
    if resource_bundle is not None:
        project_context_prompt = _build_project_context_prompt(activation)
        if project_context_prompt:
            sections.append(
                PromptSection(
                    "project-context",
                    project_context_prompt,
                    kind="resource",
                )
            )
            resource_fragments.append(project_context_prompt)
        for index, cleaned_fragment in enumerate(
            _iter_non_context_prompt_fragments(activation)
        ):
            sections.append(
                PromptSection(
                    f"resource-{index}",
                    cleaned_fragment,
                    kind="resource",
                )
            )
            resource_fragments.append(cleaned_fragment)
    skill_prompt = _build_skill_prompt(activation)
    if skill_prompt:
        sections.append(PromptSection("available-skills", skill_prompt, kind="skill"))
        resource_fragments.append(skill_prompt)
    cleaned_tool_prompt = (
        tool_prompt.strip()
        if isinstance(tool_prompt, str) and tool_prompt.strip()
        else ""
    )
    if not cleaned_tool_prompt:
        cleaned_tool_prompt = _build_tool_prompt_from_definitions(tool_definitions)
    if not cleaned_tool_prompt:
        cleaned_tool_prompt = _build_tool_prompt_from_tools(tools)
    if cleaned_tool_prompt:
        sections.append(
            PromptSection("available-tools", cleaned_tool_prompt, kind="tool")
        )
    runtime_footer = _build_runtime_footer(resource_bundle)
    if runtime_footer:
        sections.append(PromptSection("runtime-footer", runtime_footer, kind="runtime"))
    prepared = (prompt_section_composer or PromptSectionComposer()).compose(sections)
    return PromptAssembly(
        system_prompt=prepared.text,
        tool_prompt=cleaned_tool_prompt,
        resource_fragments=tuple(resource_fragments),
    )


def assemble_system_prompt(
    *, base_prompt: str | None = None, resource_bundle: ResourceBundle | None = None
) -> str:
    return assemble_prompt(
        base_prompt=base_prompt, resource_bundle=resource_bundle
    ).system_prompt
