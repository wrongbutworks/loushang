from __future__ import annotations

from loushang.method import MethodDescriptor, MethodRegistry, MethodSelector


def _method(id: str, name: str) -> MethodDescriptor:
    return MethodDescriptor(id=id, name=name, description="", content="Guidance.", kind="method_resource")


def test_method_selector_matches_exact_id_or_name_from_registry() -> None:
    review = _method("method:task:review", "review")
    selector = MethodSelector(MethodRegistry([review]))

    assert selector.select("method:task:review") == review
    assert selector.select("review") == review
    assert selector.select("rev") is None


def test_method_selector_matches_exact_id_or_name_from_descriptor_list() -> None:
    review = _method("method:task:review", "review")
    selector = MethodSelector([review])

    assert selector.select("review") == review
    assert selector.select("Review") is None
