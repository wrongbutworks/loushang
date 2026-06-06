from __future__ import annotations

from loushang.method import (
    MethodApplicability,
    MethodCompiler,
    MethodDescriptor,
    MethodProjector,
)


def test_method_projector_builds_stable_system_guidance() -> None:
    descriptor = MethodDescriptor(
        id="method:task:review",
        name="review",
        description="Review changes.",
        content="Review the diff carefully.",
        kind="method_resource",
        meta_role="VALIDATOR",
        metadata={"frontmatter": {"temperature": "0.2"}},
    )
    plan = MethodCompiler().compile(descriptor)
    step = plan.steps[0]

    projection = MethodProjector().project(plan, step)

    assert projection.method_id == "method:task:review"
    assert projection.step_id == "main"
    assert projection.system_guidance == (
        "Use the following method guidance when performing this turn:\n\n"
        "Review the diff carefully."
    )
    assert projection.meta_role == "VALIDATOR"
    assert projection.temperature == 0.2


def test_method_projector_preserves_step_policy_metadata() -> None:
    descriptor = MethodDescriptor(
        id="method:task:review",
        name="review",
        description="Review changes.",
        content="Review the diff carefully.",
        kind="method_resource",
        metadata={
            "frontmatter": {
                "plan_mode": "fixed",
                "steps": ["inspect"],
                "step_constraints": {
                    "inspect": {
                        "level": "reasoned",
                        "requires_reason": True,
                    },
                },
                "step_audit": {
                    "inspect": {
                        "record": ["status", "reason"],
                    },
                },
            },
        },
    )
    plan = MethodCompiler().compile(descriptor)
    projection = MethodProjector().project(plan, plan.steps[0])

    assert projection.metadata["source_constraint"] == {
        "level": "reasoned",
        "requires_reason": True,
    }
    assert projection.metadata["source_audit"] == {"record": ["status", "reason"]}


def test_method_projector_exposes_structured_plan_and_step_facts() -> None:
    applicability = MethodApplicability(
        domains=("coding",),
        task_types=("reviewing",),
        tags={"method_family": ("verification",)},
    )
    descriptor = MethodDescriptor(
        id="method:task:review",
        name="review",
        description="Review changes.",
        content="Review the diff carefully.",
        kind="method_resource",
        element_type="task",
        meta_role="VALIDATOR",
        phase="VERIFY",
        metadata={
            "frontmatter": {
                "plan_mode": "fixed",
                "steps": ["inspect", "verify"],
                "step_titles": {
                    "inspect": "Inspect current changes",
                    "verify": "Run focused checks",
                },
            },
        },
        applicability=applicability,
    )
    plan = MethodCompiler().compile(descriptor)

    projection = MethodProjector().project(plan, plan.steps[1])

    assert projection.metadata["plan_facts"] == {
        "plan_id": "plan:method:task:review",
        "method_id": "method:task:review",
        "mode": "fixed",
        "phase": "VERIFY",
        "activity": None,
        "task": None,
        "metadata": {
            "method_kind": "method_resource",
            "element_type": "task",
            "plan_mode": "fixed",
            "step_count": 2,
        },
        "applicability": {
            "domains": ("coding",),
            "task_types": ("reviewing",),
            "contexts": (),
            "artifact_types": (),
            "modalities": (),
            "toolchains": (),
            "lifecycle": (),
            "capabilities": (),
            "complexity": None,
            "risk": None,
            "tags": {"method_family": ("verification",)},
        },
    }
    assert projection.metadata["step_facts"] == {
        "step_id": "verify",
        "title": "Run focused checks",
        "executor": "current_agent",
        "role_variant": None,
        "step_index": 1,
        "step_count": 2,
        "applicability": {
            "domains": ("coding",),
            "task_types": ("reviewing",),
            "contexts": (),
            "artifact_types": (),
            "modalities": (),
            "toolchains": (),
            "lifecycle": (),
            "capabilities": (),
            "complexity": None,
            "risk": None,
            "tags": {"method_family": ("verification",)},
        },
    }


def test_method_projector_handles_empty_content() -> None:
    descriptor = MethodDescriptor(id="skill:empty", name="empty", description="", content="", kind="skill_backed")
    plan = MethodCompiler().compile(descriptor)

    projection = MethodProjector().project(plan, plan.steps[0])

    assert projection.system_guidance == "Use the following method guidance when performing this turn:\n\n"
