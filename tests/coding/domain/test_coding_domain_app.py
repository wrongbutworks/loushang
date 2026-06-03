from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from loushang.coding.domain import (
    DEFAULT_GUIDANCE_TEMPLATE,
    CodingDomainApp,
    CodingDomainPreparedTurn,
    CodingDomainRequest,
    MethodPolicy,
)


def test_coding_domain_request_defaults() -> None:
    request = CodingDomainRequest(
        user_input="review this change",
        cwd=Path("/tmp/project"),
    )

    assert request.user_input == "review this change"
    assert request.cwd == Path("/tmp/project")
    assert request.method is None
    assert request.metadata == {}


def test_coding_domain_prepared_turn_defaults() -> None:
    prepared = CodingDomainPreparedTurn(prepared_prompt="review this change")

    assert prepared.prepared_prompt == "review this change"
    assert prepared.method_id is None
    assert prepared.method_guidance is None
    assert prepared.metadata == {}


def test_coding_domain_types_are_frozen() -> None:
    request = CodingDomainRequest(user_input="hello", cwd=Path("/tmp/project"))

    with pytest.raises(FrozenInstanceError):
        request.user_input = "changed"  # type: ignore[misc]


def test_method_policy_defaults_to_explicit_without_selection() -> None:
    policy = MethodPolicy()

    assert policy.mode == "explicit"
    assert policy.selected_method is None


def test_method_policy_off_factory() -> None:
    policy = MethodPolicy.off()

    assert policy.mode == "off"
    assert policy.selected_method is None


def test_method_policy_explicit_factory() -> None:
    policy = MethodPolicy.explicit("review")

    assert policy.mode == "explicit"
    assert policy.selected_method == "review"


def test_prepare_turn_without_method_keeps_prompt_unchanged(tmp_path: Path) -> None:
    request = CodingDomainRequest(user_input="review this change", cwd=tmp_path)

    prepared = CodingDomainApp().prepare_turn(request)

    assert prepared.prepared_prompt == "review this change"
    assert prepared.method_id is None
    assert prepared.method_guidance is None


def test_prepare_turn_with_skill_backed_method_adds_guidance(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: review\n"
        "description: Review changes.\n"
        "type: task\n"
        "---\n\n"
        "Review code carefully.",
        encoding="utf-8",
    )
    request = CodingDomainRequest(
        user_input="check src/app.py",
        cwd=tmp_path,
        method="review",
    )

    prepared = CodingDomainApp().prepare_turn(request)

    assert prepared.method_id == "skill:review"
    assert prepared.method_guidance is not None
    assert "Review code carefully." in prepared.method_guidance
    assert prepared.prepared_prompt == DEFAULT_GUIDANCE_TEMPLATE.format(
        guidance=prepared.method_guidance,
        user_input="check src/app.py",
    )


def test_prepare_turn_with_method_resource_adds_guidance(tmp_path: Path) -> None:
    method_dir = tmp_path / "methods" / "task" / "review"
    method_dir.mkdir(parents=True)
    (method_dir / "SKILL.md").write_text(
        "---\n"
        "name: review\n"
        "description: Review changes.\n"
        "type: task\n"
        "meta_role: VALIDATOR\n"
        "---\n\n"
        "Use the review method.",
        encoding="utf-8",
    )
    request = CodingDomainRequest(
        user_input="check src/app.py",
        cwd=tmp_path,
        method="method:task:review",
    )

    prepared = CodingDomainApp().prepare_turn(request)

    assert prepared.method_id == "method:task:review"
    assert prepared.method_guidance is not None
    assert "Use the review method." in prepared.method_guidance
    assert prepared.metadata["meta_role"] == "VALIDATOR"
    assert prepared.prepared_prompt.endswith("User request:\n\ncheck src/app.py")


def test_prepare_turn_missing_method_raises_value_error(tmp_path: Path) -> None:
    request = CodingDomainRequest(user_input="hello", cwd=tmp_path, method="missing")

    with pytest.raises(ValueError, match="method not found: missing"):
        CodingDomainApp().prepare_turn(request)


def test_prepare_turn_empty_guidance_keeps_prompt_but_records_method(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "empty"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("", encoding="utf-8")
    request = CodingDomainRequest(
        user_input="hello",
        cwd=tmp_path,
        method="empty",
    )

    prepared = CodingDomainApp().prepare_turn(request)

    assert prepared.method_id == "skill:empty"
    assert prepared.method_guidance is None
    assert prepared.prepared_prompt == "hello"
