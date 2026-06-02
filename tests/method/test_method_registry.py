from __future__ import annotations

import pytest

from loushang.method import MethodDescriptor, MethodRegistry


def _method(id: str, name: str | None = None) -> MethodDescriptor:
    return MethodDescriptor(
        id=id,
        name=name or id,
        description="",
        content="Guidance.",
        kind="method_resource",
    )


def test_method_registry_lists_and_gets_by_id_or_name() -> None:
    review = _method("method:task:review", name="review")
    registry = MethodRegistry([review])

    assert registry.list_methods() == [review]
    assert registry.get_method("method:task:review") == review
    assert registry.get_method("review") == review
    assert registry.get_method("missing") is None


def test_method_registry_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate method id"):
        MethodRegistry([_method("method:review", "review"), _method("method:review", "review-copy")])


def test_method_registry_selected_state_is_in_memory() -> None:
    review = _method("method:task:review", name="review")
    registry = MethodRegistry([review])

    assert registry.get_selected_method() is None
    assert registry.select_method("review") == review
    assert registry.get_selected_method() == review
    assert registry.clear_selected_method() is None
    assert registry.get_selected_method() is None


def test_method_registry_missing_selection_returns_none() -> None:
    registry = MethodRegistry()

    assert registry.select_method("missing") is None
    assert registry.get_selected_method() is None
