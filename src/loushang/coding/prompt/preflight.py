from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from loushang.coding.commands.slash import split_slash_command
from loushang.coding.frontmatter import strip_frontmatter
from loushang.coding.loader import PromptFragmentDescriptor, ResourceBundle, ResourceDiagnostic, SkillDescriptor
from loushang.coding.prompt.templates import (
    parse_prompt_template_args,
    prompt_template_has_args,
    substitute_prompt_template_args,
)


@dataclass(frozen=True)
class PromptPreflightResult:
    text: str
    consumed: bool = False
    diagnostics: tuple[ResourceDiagnostic, ...] = field(default_factory=tuple)


def preflight_user_input(
    text: str,
    *,
    resource_bundle: ResourceBundle | None = None,
) -> PromptPreflightResult:
    parsed = split_slash_command(text)
    if parsed is None:
        return PromptPreflightResult(text=text)

    command_name, args = parsed
    if command_name.startswith("skill:"):
        skill_name = command_name.removeprefix("skill:")
        skill = _find_skill(skill_name, resource_bundle)
        if skill is None:
            return PromptPreflightResult(
                text=text,
                diagnostics=(
                    ResourceDiagnostic(
                        code="unresolved_skill_reference",
                        message=f"Skill reference '/skill:{skill_name}' did not match any discovered skill.",
                        resource_id=skill_name,
                        resource_type="skill",
                    ),
                ),
            )
        body = strip_frontmatter(skill.content or "").strip()
        base_dir = skill.source_path.parent.as_posix()
        skill_block = (
            f'<skill name="{skill.name}" location="{skill.source_path.as_posix()}">\n'
            f"References are relative to {base_dir}.\n\n"
            f"{body}\n"
            "</skill>"
        )
        return PromptPreflightResult(text=_append_args(skill_block, args))

    prompt = _find_prompt(command_name, resource_bundle)
    if prompt is None:
        return PromptPreflightResult(
            text=text,
            diagnostics=(
                ResourceDiagnostic(
                    code="unresolved_prompt_reference",
                    message=f"Prompt reference '/{command_name}' did not match any discovered prompt template.",
                    resource_id=command_name,
                    resource_type="prompt",
                ),
            ),
        )
    prompt_text = strip_frontmatter(prompt.text).strip()
    return PromptPreflightResult(text=_expand_prompt_template(prompt_text, args))


async def preflight_user_input_async(
    text: str,
    *,
    resource_bundle: ResourceBundle | None = None,
    execute_command: Callable[[str, str], Awaitable[object | None]] | None = None,
) -> PromptPreflightResult:
    parsed = split_slash_command(text)
    if parsed is None:
        return PromptPreflightResult(text=text)

    command_name, args = parsed
    if execute_command is not None:
        await execute_command(command_name, args)
        return PromptPreflightResult(text=text, consumed=True)

    if command_name.startswith("skill:"):
        skill_name = command_name.removeprefix("skill:")
        skill = _find_skill(skill_name, resource_bundle)
        if skill is None:
            return PromptPreflightResult(
                text=text,
                diagnostics=(
                    ResourceDiagnostic(
                        code="unresolved_skill_reference",
                        message=f"Skill reference '/skill:{skill_name}' did not match any discovered skill.",
                        resource_id=skill_name,
                        resource_type="skill",
                    ),
                ),
            )
        body = strip_frontmatter(skill.content or "").strip()
        base_dir = skill.source_path.parent.as_posix()
        skill_block = (
            f'<skill name="{skill.name}" location="{skill.source_path.as_posix()}">\n'
            f"References are relative to {base_dir}.\n\n"
            f"{body}\n"
            "</skill>"
        )
        return PromptPreflightResult(text=_append_args(skill_block, args))

    prompt = _find_prompt(command_name, resource_bundle)
    if prompt is None:
        return PromptPreflightResult(
            text=text,
            diagnostics=(
                ResourceDiagnostic(
                    code="unresolved_prompt_reference",
                    message=f"Prompt reference '/{command_name}' did not match any discovered prompt template.",
                    resource_id=command_name,
                    resource_type="prompt",
                ),
            ),
        )
    prompt_text = strip_frontmatter(prompt.text).strip()
    return PromptPreflightResult(text=_expand_prompt_template(prompt_text, args))


def _expand_prompt_template(content: str, args: str) -> str:
    if not args:
        return content
    if prompt_template_has_args(content):
        return substitute_prompt_template_args(content, parse_prompt_template_args(args))
    return _append_args(content, args)


def _append_args(content: str, args: str) -> str:
    if not args:
        return content
    return f"{content}\n\n{args}"


def _find_prompt(name: str, resource_bundle: ResourceBundle | None) -> PromptFragmentDescriptor | None:
    if resource_bundle is None:
        return None
    for prompt in resource_bundle.prompts:
        if prompt.name == name or prompt.canonical_name == name or prompt.id == name:
            return prompt
    return None


def _find_skill(name: str, resource_bundle: ResourceBundle | None) -> SkillDescriptor | None:
    if resource_bundle is None:
        return None
    for skill in resource_bundle.skills:
        if not skill.enabled:
            continue
        if skill.name == name or skill.canonical_name == name or skill.id == name:
            return skill
    return None


__all__ = ["PromptPreflightResult", "preflight_user_input", "preflight_user_input_async"]
