from __future__ import annotations

from loushang.method.types import (
    MethodContext,
    MethodPlan,
    MethodProjection,
    MethodStep,
)


class MethodProjector:
    def project(
        self,
        plan: MethodPlan,
        step: MethodStep,
        context: MethodContext | None = None,
    ) -> MethodProjection:
        _ = context
        content = step.projection.get("content")
        method_content = content if isinstance(content, str) else ""
        return MethodProjection(
            method_id=plan.method_id,
            step_id=step.id,
            system_guidance=f"Use the following method guidance when performing this turn:\n\n{method_content}",
            meta_role=_string_projection_value(step, "meta_role"),
            role_variant=step.role_variant,
            temperature=_float_projection_value(step, "temperature"),
            metadata={
                "source_projection": dict(step.projection),
                "source_constraint": dict(step.constraint),
                "source_audit": dict(step.audit),
            },
        )


def _string_projection_value(step: MethodStep, key: str) -> str | None:
    value = step.projection.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _float_projection_value(step: MethodStep, key: str) -> float | None:
    value = step.projection.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


__all__ = ["MethodProjector"]
