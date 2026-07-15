from __future__ import annotations


def _item(
    item_id: str,
    tokens: int,
    *,
    group_id: str | None = None,
    priority: int = 0,
    pinned: bool = False,
):
    from loushang.harness.context import ContextItem

    return ContextItem(
        item_id=item_id,
        kind="fixture",
        content=item_id,
        estimated_tokens=tokens,
        group_id=group_id,
        priority=priority,
        pinned=pinned,
    )


def test_recent_packing_keeps_atomic_groups_and_source_order() -> None:
    from loushang.harness.context import ContextBundle, ContextPacker, PackingRequest

    bundle = ContextBundle(
        items=(
            _item("old", 4),
            _item("call", 3, group_id="tool"),
            _item("result", 3, group_id="tool"),
            _item("recent", 4),
        )
    )

    packed = ContextPacker().pack(
        PackingRequest(bundle=bundle, target_tokens=10, order="recent")
    )

    assert packed.selected_item_ids == ("call", "result", "recent")
    assert packed.omitted_item_ids == ("old",)
    assert packed.bundle.source_tokens == 10


def test_priority_and_pinning_are_group_properties() -> None:
    from loushang.harness.context import ContextBundle, ContextPacker, PackingRequest

    bundle = ContextBundle(
        items=(
            _item("claim", 3, group_id="evidence", priority=1),
            _item("evidence", 3, group_id="evidence", priority=9),
            _item("ordinary", 4, priority=5),
            _item("pinned-a", 2, group_id="state"),
            _item("pinned-b", 2, group_id="state", pinned=True),
        )
    )

    packed = ContextPacker().pack(
        PackingRequest(bundle=bundle, target_tokens=10, order="priority")
    )

    assert packed.selected_item_ids == (
        "claim",
        "evidence",
        "pinned-a",
        "pinned-b",
    )
    assert packed.omitted_item_ids == ("ordinary",)


def test_non_contiguous_group_is_atomic_and_diagnosed() -> None:
    from loushang.harness.context import ContextBundle, ContextPacker, PackingRequest

    bundle = ContextBundle(
        items=(
            _item("first", 2, group_id="g"),
            _item("middle", 2),
            _item("last", 2, group_id="g"),
        )
    )

    packed = ContextPacker().pack(
        PackingRequest(bundle=bundle, target_tokens=4, order="insertion")
    )

    assert packed.selected_item_ids == ("first", "last")
    assert [diagnostic.code for diagnostic in packed.diagnostics] == [
        "non_contiguous_context_group"
    ]


def test_pinned_overflow_is_explicit() -> None:
    from loushang.harness.context import ContextBundle, ContextPacker, PackingRequest

    bundle = ContextBundle(items=(_item("state", 8, pinned=True), _item("tail", 2)))

    packed = ContextPacker().pack(
        PackingRequest(bundle=bundle, target_tokens=5, order="recent")
    )

    assert packed.selected_item_ids == ("state",)
    assert packed.overflow_tokens == 3
    assert packed.diagnostics[-1].code == "pinned_context_overflow"


def test_bundle_rejects_duplicate_ids_and_normalizes_negative_tokens() -> None:
    import pytest

    from loushang.harness.context import ContextBundle

    assert _item("negative", -4).estimated_tokens == 0
    with pytest.raises(ValueError, match="unique"):
        ContextBundle(items=(_item("same", 1), _item("same", 2)))
