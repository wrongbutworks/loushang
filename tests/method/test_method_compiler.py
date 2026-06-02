from __future__ import annotations

from loushang.method import MethodCompiler, MethodContext, MethodDescriptor


def test_method_compiler_returns_single_turn_plan_with_main_step() -> None:
    descriptor = MethodDescriptor(
        id="method:task:review",
        name="review",
        description="Review changes.",
        content="Review the diff carefully.",
        kind="method_resource",
        element_type="task",
        meta_role="VALIDATOR",
        phase="VERIFY",
        metadata={"frontmatter": {"temperature": "0.2"}},
    )

    plan = MethodCompiler().compile(descriptor, MethodContext(domain="coding"))

    assert plan.id == "plan:method:task:review"
    assert plan.method_id == "method:task:review"
    assert plan.mode == "single_turn"
    assert plan.phase == "VERIFY"
    assert plan.activity is None
    assert plan.task is None
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.id == "main"
    assert step.title == "review"
    assert step.executor == "current_agent"
    assert step.role_variant is None
    assert step.projection["content"] == "Review the diff carefully."
    assert step.projection["meta_role"] == "VALIDATOR"
    assert step.projection["temperature"] == 0.2


def test_method_compiler_uses_none_for_missing_hints() -> None:
    descriptor = MethodDescriptor(
        id="skill:debug",
        name="debug",
        description="",
        content="Debug failures.",
        kind="skill_backed",
    )

    plan = MethodCompiler().compile(descriptor)

    assert plan.phase is None
    assert plan.steps[0].projection["meta_role"] is None
    assert plan.steps[0].projection["temperature"] is None
