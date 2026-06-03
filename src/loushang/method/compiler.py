from __future__ import annotations

from collections.abc import Mapping as MappingABC

from loushang.method.types import (
    MethodContext,
    MethodDescriptor,
    MethodPlan,
    MethodStep,
)


class MethodCompiler:
    def compile(self, descriptor: MethodDescriptor, context: MethodContext | None = None) -> MethodPlan:
        _ = context
        frontmatter = _frontmatter_hint(descriptor.metadata)
        plan_mode = _string_hint(frontmatter, "plan_mode")
        if plan_mode == "fixed":
            return _compile_fixed_plan(descriptor, frontmatter=frontmatter)
        if plan_mode not in (None, "single_turn"):
            raise ValueError(f"unsupported MethodPlan mode: {plan_mode}")
        step = MethodStep(
            id="main",
            title=descriptor.name,
            executor="current_agent",
            projection={
                "content": descriptor.content,
                "meta_role": descriptor.meta_role,
                "temperature": _temperature_hint(descriptor.metadata),
            },
        )
        return MethodPlan(
            id=f"plan:{descriptor.id}",
            method_id=descriptor.id,
            mode="single_turn",
            steps=(step,),
            phase=descriptor.phase,
            metadata={
                "method_kind": descriptor.kind,
                "element_type": descriptor.element_type,
            },
            applicability=descriptor.applicability,
        )


def _compile_fixed_plan(descriptor: MethodDescriptor, *, frontmatter: MappingABC[str, object]) -> MethodPlan:
    step_ids = _fixed_step_ids(frontmatter, descriptor=descriptor)
    step_titles = _string_map_hint(frontmatter, "step_titles")
    step_guidance = _string_map_hint(frontmatter, "step_guidance")
    temperature = _temperature_hint(descriptor.metadata)
    steps = tuple(
        MethodStep(
            id=step_id,
            title=step_titles.get(step_id) or step_id,
            executor="current_agent",
            projection={
                "content": _fixed_step_content(
                    method_content=descriptor.content,
                    step_id=step_id,
                    step_title=step_titles.get(step_id) or step_id,
                    step_guidance=step_guidance.get(step_id),
                ),
                "method_content": descriptor.content,
                "step_guidance": step_guidance.get(step_id),
                "step_index": index,
                "step_count": len(step_ids),
                "meta_role": descriptor.meta_role,
                "temperature": temperature,
            },
            applicability=descriptor.applicability,
        )
        for index, step_id in enumerate(step_ids)
    )
    return MethodPlan(
        id=f"plan:{descriptor.id}",
        method_id=descriptor.id,
        mode="fixed",
        steps=steps,
        phase=descriptor.phase,
        metadata={
            "method_kind": descriptor.kind,
            "element_type": descriptor.element_type,
            "plan_mode": "fixed",
            "step_count": len(steps),
        },
        applicability=descriptor.applicability,
    )


def _fixed_step_ids(frontmatter: MappingABC[str, object], *, descriptor: MethodDescriptor) -> tuple[str, ...]:
    raw_steps = frontmatter.get("steps")
    if not isinstance(raw_steps, list | tuple) or not raw_steps:
        raise ValueError(f"fixed MethodPlan requires non-empty steps: {descriptor.id}")
    if not all(isinstance(step_id, str) and step_id for step_id in raw_steps):
        raise ValueError(f"fixed MethodPlan step ids must be strings: {descriptor.id}")
    return tuple(raw_steps)


def _fixed_step_content(
    *,
    method_content: str,
    step_id: str,
    step_title: str,
    step_guidance: str | None,
) -> str:
    parts = [method_content]
    if step_guidance:
        parts.append(f"Step {step_id} - {step_title}:\n{step_guidance}")
    else:
        parts.append(f"Step {step_id} - {step_title}")
    return "\n\n".join(part for part in parts if part)


def _frontmatter_hint(metadata: MappingABC[str, object]) -> MappingABC[str, object]:
    frontmatter = metadata.get("frontmatter")
    if isinstance(frontmatter, MappingABC):
        return frontmatter
    return {}


def _string_hint(frontmatter: MappingABC[str, object], key: str) -> str | None:
    value = frontmatter.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _string_map_hint(frontmatter: MappingABC[str, object], key: str) -> dict[str, str]:
    value = frontmatter.get(key)
    if not isinstance(value, MappingABC):
        return {}
    return {
        item_key: item_value
        for item_key, item_value in value.items()
        if isinstance(item_key, str) and item_key and isinstance(item_value, str) and item_value
    }


def _temperature_hint(metadata: MappingABC[str, object]) -> float | None:
    frontmatter = _frontmatter_hint(metadata)
    value = frontmatter.get("temperature")
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


__all__ = ["MethodCompiler"]
