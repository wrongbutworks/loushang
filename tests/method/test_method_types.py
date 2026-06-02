from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from loushang.method import (
    MethodContext,
    MethodDescriptor,
    MethodPlan,
    MethodProjection,
    MethodStep,
)


def test_method_descriptor_defaults_and_taxonomy_hints() -> None:
    descriptor = MethodDescriptor(
        id="skill:code-review",
        name="code-review",
        description="Review code changes",
        content="Review the diff carefully.",
        kind="skill_backed",
        element_type="task",
        domain="coding",
        meta_role="VALIDATOR",
        phase="VERIFY",
        source_path="skills/code-review/SKILL.md",
        version="1",
        metadata={"frontmatter": {"type": "task"}},
    )

    assert descriptor.id == "skill:code-review"
    assert descriptor.kind == "skill_backed"
    assert descriptor.element_type == "task"
    assert descriptor.domain == "coding"
    assert descriptor.meta_role == "VALIDATOR"
    assert descriptor.phase == "VERIFY"
    assert descriptor.metadata["frontmatter"] == {"type": "task"}

    with pytest.raises(FrozenInstanceError):
        descriptor.name = "changed"  # type: ignore[misc]


def test_method_context_defaults_are_small() -> None:
    context = MethodContext()

    assert context.domain is None
    assert context.task is None
    assert context.metadata == {}


def test_method_plan_and_step_support_single_turn_defaults() -> None:
    step = MethodStep(id="main", title="Main", executor="current_agent")
    plan = MethodPlan(id="plan:skill:review", method_id="skill:review", mode="single_turn", steps=(step,))

    assert plan.steps == (step,)
    assert plan.phase is None
    assert plan.activity is None
    assert plan.task is None
    assert step.role_variant is None
    assert step.projection == {}


def test_method_projection_defaults_and_optional_role_hints() -> None:
    projection = MethodProjection(
        method_id="skill:review",
        step_id="main",
        system_guidance="Use this method.",
        meta_role="VALIDATOR",
        role_variant="reviewer",
        temperature=0.2,
    )

    assert projection.system_guidance == "Use this method."
    assert projection.meta_role == "VALIDATOR"
    assert projection.role_variant == "reviewer"
    assert projection.temperature == 0.2
    assert projection.user_guidance is None
    assert projection.allowed_skills == ()
    assert projection.suggested_tools == ()
    assert projection.expected_artifacts == ()
    assert projection.approval_gates == ()
    assert projection.metadata == {}
