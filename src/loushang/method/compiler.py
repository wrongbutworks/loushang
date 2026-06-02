from __future__ import annotations

from collections.abc import Mapping as MappingABC

from loushang.method.types import MethodContext, MethodDescriptor, MethodPlan, MethodStep


class MethodCompiler:
    def compile(self, descriptor: MethodDescriptor, context: MethodContext | None = None) -> MethodPlan:
        _ = context
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
        )


def _temperature_hint(metadata: MappingABC[str, object]) -> float | None:
    frontmatter = metadata.get("frontmatter")
    if not isinstance(frontmatter, MappingABC):
        return None
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
