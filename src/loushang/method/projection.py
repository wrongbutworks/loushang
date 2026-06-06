from __future__ import annotations

from loushang.method.types import (
    MethodApplicability,
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
                "plan_facts": _plan_facts(plan),
                "step_facts": _step_facts(plan, step),
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


def _plan_facts(plan: MethodPlan) -> dict[str, object]:
    return {
        "plan_id": plan.id,
        "method_id": plan.method_id,
        "mode": plan.mode,
        "phase": plan.phase,
        "activity": plan.activity,
        "task": plan.task,
        "metadata": dict(plan.metadata),
        "applicability": _applicability_facts(plan.applicability),
    }


def _step_facts(plan: MethodPlan, step: MethodStep) -> dict[str, object]:
    return {
        "step_id": step.id,
        "title": step.title,
        "executor": step.executor,
        "role_variant": step.role_variant,
        "step_index": _step_index(plan, step),
        "step_count": len(plan.steps),
        "applicability": _applicability_facts(step.applicability),
    }


def _step_index(plan: MethodPlan, step: MethodStep) -> int | None:
    for index, candidate in enumerate(plan.steps):
        if candidate is step:
            return index
    for index, candidate in enumerate(plan.steps):
        if candidate.id == step.id:
            return index
    value = step.projection.get("step_index")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _applicability_facts(applicability: MethodApplicability) -> dict[str, object]:
    return {
        "domains": applicability.domains,
        "task_types": applicability.task_types,
        "contexts": applicability.contexts,
        "artifact_types": applicability.artifact_types,
        "modalities": applicability.modalities,
        "toolchains": applicability.toolchains,
        "lifecycle": applicability.lifecycle,
        "capabilities": applicability.capabilities,
        "complexity": applicability.complexity,
        "risk": applicability.risk,
        "tags": {key: tuple(values) for key, values in applicability.tags.items()},
    }


__all__ = ["MethodProjector"]
