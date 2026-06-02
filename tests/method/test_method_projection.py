from __future__ import annotations

from loushang.method import MethodCompiler, MethodDescriptor, MethodProjector


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


def test_method_projector_handles_empty_content() -> None:
    descriptor = MethodDescriptor(id="skill:empty", name="empty", description="", content="", kind="skill_backed")
    plan = MethodCompiler().compile(descriptor)

    projection = MethodProjector().project(plan, plan.steps[0])

    assert projection.system_guidance == "Use the following method guidance when performing this turn:\n\n"
