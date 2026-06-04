from __future__ import annotations

import pytest

from loushang.method import (
    MethodApplicability,
    MethodCompiler,
    MethodContext,
    MethodDescriptor,
)


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


def test_method_compiler_returns_fixed_plan_from_flat_step_metadata() -> None:
    applicability = MethodApplicability(domains=("coding",), task_types=("reviewing",))
    descriptor = MethodDescriptor(
        id="method:task:review-with-tests",
        name="review-with-tests",
        description="Review and verify changes.",
        content="Use the review method.",
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
                "step_guidance": {
                    "inspect": "Read changed files and summarize intent.",
                    "verify": "Run focused tests or explain why they cannot run.",
                },
                "step_constraints": {
                    "inspect": {
                        "level": "reasoned",
                        "can_merge": True,
                        "requires_reason": True,
                    },
                    "verify": {
                        "level": "evidence",
                        "can_skip": True,
                        "requires_evidence": True,
                    },
                },
                "step_audit": {
                    "inspect": {
                        "record": ["status", "reason"],
                    },
                    "verify": {
                        "record": ["status", "reason", "evidence"],
                    },
                },
                "temperature": "0.2",
            },
        },
        applicability=applicability,
    )

    plan = MethodCompiler().compile(descriptor, MethodContext(domain="coding"))

    assert plan.id == "plan:method:task:review-with-tests"
    assert plan.method_id == "method:task:review-with-tests"
    assert plan.mode == "fixed"
    assert plan.phase == "VERIFY"
    assert plan.applicability == applicability
    assert plan.metadata["method_kind"] == "method_resource"
    assert plan.metadata["element_type"] == "task"
    assert plan.metadata["plan_mode"] == "fixed"
    assert plan.metadata["step_count"] == 2
    assert [step.id for step in plan.steps] == ["inspect", "verify"]
    assert [step.title for step in plan.steps] == ["Inspect current changes", "Run focused checks"]

    inspect, verify = plan.steps
    assert inspect.executor == "current_agent"
    assert inspect.projection["content"] == (
        "Use the review method.\n\n"
        "Step inspect - Inspect current changes:\n"
        "Read changed files and summarize intent."
    )
    assert inspect.projection["method_content"] == "Use the review method."
    assert inspect.projection["step_guidance"] == "Read changed files and summarize intent."
    assert inspect.projection["step_index"] == 0
    assert inspect.projection["step_count"] == 2
    assert inspect.projection["meta_role"] == "VALIDATOR"
    assert inspect.projection["temperature"] == 0.2
    assert inspect.constraint == {
        "level": "reasoned",
        "can_merge": True,
        "requires_reason": True,
    }
    assert inspect.audit == {"record": ["status", "reason"]}
    assert verify.projection["content"].endswith("Run focused tests or explain why they cannot run.")
    assert verify.constraint == {
        "level": "evidence",
        "can_skip": True,
        "requires_evidence": True,
    }
    assert verify.audit == {"record": ["status", "reason", "evidence"]}


def test_method_compiler_rejects_fixed_plan_without_steps() -> None:
    descriptor = MethodDescriptor(
        id="method:task:broken",
        name="broken",
        description="",
        content="Broken fixed plan.",
        kind="method_resource",
        metadata={"frontmatter": {"plan_mode": "fixed"}},
    )

    with pytest.raises(ValueError, match="fixed MethodPlan requires non-empty steps"):
        MethodCompiler().compile(descriptor)


def test_method_compiler_rejects_non_string_fixed_step_ids() -> None:
    descriptor = MethodDescriptor(
        id="method:task:broken",
        name="broken",
        description="",
        content="Broken fixed plan.",
        kind="method_resource",
        metadata={"frontmatter": {"plan_mode": "fixed", "steps": ["inspect", 3]}},
    )

    with pytest.raises(ValueError, match="fixed MethodPlan step ids must be strings"):
        MethodCompiler().compile(descriptor)


def test_method_compiler_rejects_unsupported_plan_mode() -> None:
    descriptor = MethodDescriptor(
        id="method:task:graph",
        name="graph",
        description="",
        content="Graph method.",
        kind="method_resource",
        metadata={"frontmatter": {"plan_mode": "graph"}},
    )

    with pytest.raises(ValueError, match="unsupported MethodPlan mode: graph"):
        MethodCompiler().compile(descriptor)
