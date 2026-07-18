from __future__ import annotations

from dataclasses import dataclass

import pytest

from loushang.harness.context import (
    ConversationCompactionPlanner,
    ConversationPreviousSummary,
    ConversationRecordPorts,
    MissingPreviousSummaryPolicy,
)


@dataclass(frozen=True)
class ResearchRecord:
    record_id: str
    role: str | None = None
    tokens: int = 0
    visible: bool = True
    cut_group_boundary: bool = True
    summary: ConversationPreviousSummary[str] | None = None


def _planner(
    *,
    aggregate_tokens: int | None = None,
    group_cut_records: bool = False,
    missing_previous_summary: MissingPreviousSummaryPolicy = "error",
) -> ConversationCompactionPlanner[ResearchRecord, str]:
    return ConversationCompactionPlanner(
        ConversationRecordPorts(
            record_id=lambda record: record.record_id,
            is_visible=lambda record: record.visible,
            role=lambda record: record.role,
            estimate_tokens=lambda record: record.tokens,
            estimate_context_tokens=(
                (lambda records: aggregate_tokens)
                if aggregate_tokens is not None
                else None
            ),
            separates_cut_group=(
                (lambda record: record.cut_group_boundary)
                if group_cut_records
                else None
            ),
            previous_summary=lambda record: record.summary,
        ),
        missing_previous_summary=missing_previous_summary,
    )


def test_groups_visible_records_into_product_neutral_turns() -> None:
    turns = _planner().group_turns(
        [
            ResearchRecord("metadata", visible=False),
            ResearchRecord("u1", role="user", tokens=3),
            ResearchRecord("a1", role="assistant", tokens=5),
            ResearchRecord("tool1", role="tool", tokens=7),
            ResearchRecord("u2", role="user", tokens=11),
            ResearchRecord("a2", role="assistant", tokens=13),
        ]
    )

    assert tuple(turn.record_ids for turn in turns) == (
        ("u1", "a1", "tool1"),
        ("u2", "a2"),
    )
    assert tuple(turn.estimated_tokens for turn in turns) == (15, 24)


def test_plans_complete_turn_retention_and_records_ids() -> None:
    records = [
        ResearchRecord("u1", role="user", tokens=20),
        ResearchRecord("a1", role="assistant", tokens=20),
        ResearchRecord("index", visible=False),
        ResearchRecord("u2", role="user", tokens=2),
        ResearchRecord("a2", role="assistant", tokens=3),
    ]

    plan = _planner().plan(records, keep_recent_tokens=5)

    assert plan.previous_summary is None
    assert plan.first_kept_record_id == "u2"
    assert plan.summarized_record_ids == ("u1", "a1")
    assert plan.turn_prefix_record_ids == ()
    assert plan.kept_record_ids == ("u2", "a2")
    assert plan.is_split_turn is False
    assert plan.estimated_record_tokens == 45
    assert plan.tokens_before == 45
    assert plan.accounted_tokens_before == 45
    assert plan.summarized_tokens == 40
    assert plan.kept_tokens == 5


def test_previous_summary_boundary_and_split_turn_are_accounted() -> None:
    records = [
        ResearchRecord("old", role="user", tokens=30),
        ResearchRecord("previous-kept", role="assistant", tokens=4),
        ResearchRecord(
            "summary-1",
            visible=False,
            summary=ConversationPreviousSummary(
                first_kept_record_id="previous-kept",
                content="Earlier research decisions",
                estimated_tokens=6,
            ),
        ),
        ResearchRecord("u2", role="user", tokens=2),
        ResearchRecord("a2", role="assistant", tokens=12),
    ]

    plan = _planner().plan(records, keep_recent_tokens=5)

    assert plan.previous_summary is not None
    assert plan.previous_summary.record_id == "summary-1"
    assert plan.previous_summary.first_kept_record_id == "previous-kept"
    assert plan.previous_summary.content == "Earlier research decisions"
    assert plan.first_kept_record_id == "a2"
    assert plan.summarized_record_ids == ("previous-kept",)
    assert plan.turn_prefix_record_ids == ("u2",)
    assert plan.kept_record_ids == ("a2",)
    assert plan.is_split_turn is True
    assert plan.previous_summary_tokens == 6
    assert plan.estimated_record_tokens == 18
    assert plan.tokens_before == 18
    assert plan.accounted_tokens_before == 24
    assert plan.summarized_tokens == 4
    assert plan.turn_prefix_tokens == 2
    assert plan.kept_tokens == 12


@pytest.mark.parametrize("first_kept_record_id", ["missing", "future"])
def test_previous_summary_boundary_is_strict_for_missing_or_future_record(
    first_kept_record_id: str,
) -> None:
    records = [
        ResearchRecord(
            "summary-1",
            visible=False,
            summary=ConversationPreviousSummary(
                first_kept_record_id=first_kept_record_id,
                content="Earlier research decisions",
            ),
        ),
        ResearchRecord("future", role="user", tokens=2),
    ]

    with pytest.raises(ValueError, match="missing or future record"):
        _planner().plan(records, keep_recent_tokens=1)


def test_previous_summary_boundary_supports_explicit_summary_only_recovery() -> None:
    records = [
        ResearchRecord("old", role="user", tokens=30),
        ResearchRecord(
            "summary-1",
            visible=False,
            summary=ConversationPreviousSummary(
                first_kept_record_id="missing",
                content="Recovered research decisions",
                estimated_tokens=6,
            ),
        ),
        ResearchRecord("recent", role="user", tokens=2),
    ]

    plan = _planner(missing_previous_summary="summary_only").plan(
        records,
        keep_recent_tokens=1,
    )

    assert plan.previous_summary is not None
    assert plan.previous_summary.content == "Recovered research decisions"
    assert plan.first_kept_record_id == "recent"
    assert plan.summarized_record_ids == ()
    assert plan.kept_record_ids == ("recent",)


def test_non_cut_role_keeps_tool_result_with_its_assistant_boundary() -> None:
    records = [
        ResearchRecord("u1", role="user", tokens=10),
        ResearchRecord("a1", role="assistant", tokens=10),
        ResearchRecord("u2", role="user", tokens=1),
        ResearchRecord("a2", role="assistant", tokens=2),
        ResearchRecord("tool2", role="tool", tokens=20),
    ]

    plan = _planner().plan(records, keep_recent_tokens=5)

    assert plan.first_kept_record_id == "a2"
    assert plan.summarized_record_ids == ("u1", "a1")
    assert plan.turn_prefix_record_ids == ("u2",)
    assert plan.kept_record_ids == ("a2", "tool2")
    assert plan.is_split_turn is True


def test_aggregate_estimator_controls_tokens_before_but_not_cut_selection() -> None:
    records = [
        ResearchRecord("u1", role="user", tokens=20),
        ResearchRecord("a1", role="assistant", tokens=20),
        ResearchRecord("u2", role="user", tokens=2),
        ResearchRecord("a2", role="assistant", tokens=3),
    ]

    plan = _planner(aggregate_tokens=120).plan(records, keep_recent_tokens=5)

    assert plan.first_kept_record_id == "u2"
    assert plan.estimated_record_tokens == 45
    assert plan.tokens_before == 120
    assert plan.accounted_tokens_before == 120


def test_cut_group_includes_adjacent_invisible_metadata_in_retained_boundary() -> None:
    records = [
        ResearchRecord("u1", role="user", tokens=20),
        ResearchRecord("a1", role="assistant", tokens=20),
        ResearchRecord("u2", role="user", tokens=2),
        ResearchRecord(
            "attachment-metadata",
            visible=False,
            cut_group_boundary=False,
        ),
        ResearchRecord("a2", role="assistant", tokens=10),
    ]

    plan = _planner(group_cut_records=True).plan(
        records,
        keep_recent_tokens=5,
    )

    assert plan.first_kept_record_id == "attachment-metadata"
    assert plan.summarized_record_ids == ("u1", "a1")
    assert plan.turn_prefix_record_ids == ("u2",)
    assert plan.kept_record_ids == ("a2",)
    assert plan.is_split_turn is True


def test_cut_group_visible_records_belong_to_only_one_partition() -> None:
    records = [
        ResearchRecord("u1", role="user", tokens=20),
        ResearchRecord("a1", role="assistant", tokens=20),
        ResearchRecord(
            "custom",
            role="user",
            tokens=2,
            cut_group_boundary=False,
        ),
        ResearchRecord("a2", role="assistant", tokens=10),
    ]

    plan = _planner(group_cut_records=True).plan(
        records,
        keep_recent_tokens=5,
    )

    assert plan.first_kept_record_id == "custom"
    assert plan.summarized_record_ids == ("u1", "a1")
    assert plan.turn_prefix_record_ids == ()
    assert plan.kept_record_ids == ("custom", "a2")
    assert set(plan.summarized_record_ids).isdisjoint(plan.kept_record_ids)
    assert set(plan.turn_prefix_record_ids).isdisjoint(plan.kept_record_ids)


def test_keeps_all_records_when_the_recent_budget_is_not_reached() -> None:
    plan = _planner().plan(
        [
            ResearchRecord("u1", role="user", tokens=2),
            ResearchRecord("a1", role="assistant", tokens=3),
        ],
        keep_recent_tokens=10,
    )

    assert plan.first_kept_record_id == "u1"
    assert plan.summarized_record_ids == ()
    assert plan.turn_prefix_record_ids == ()
    assert plan.kept_record_ids == ("u1", "a1")
    assert plan.is_split_turn is False


def test_rejects_invalid_transcript_facts() -> None:
    with pytest.raises(ValueError, match="duplicate conversation record id"):
        _planner().plan(
            [
                ResearchRecord("same", role="user"),
                ResearchRecord("same", role="assistant"),
            ],
            keep_recent_tokens=1,
        )

    with pytest.raises(ValueError, match="at least one visible record"):
        _planner().plan(
            [ResearchRecord("metadata", visible=False)],
            keep_recent_tokens=1,
        )

    with pytest.raises(ValueError, match="tokens for record u1"):
        _planner().plan(
            [ResearchRecord("u1", role="user", tokens=-1)],
            keep_recent_tokens=1,
        )

    for invalid_budget in (-1, True, 1.5, "10"):
        with pytest.raises(ValueError, match="keep recent tokens"):
            _planner().plan(
                [ResearchRecord("u1", role="user", tokens=1)],
                keep_recent_tokens=invalid_budget,  # type: ignore[arg-type]
            )


def test_requires_an_eligible_cut_point() -> None:
    with pytest.raises(ValueError, match="no eligible compaction cut point"):
        _planner().plan(
            [ResearchRecord("tool1", role="tool", tokens=10)],
            keep_recent_tokens=1,
        )


def test_zero_recent_budget_keeps_the_latest_eligible_suffix() -> None:
    plan = _planner().plan(
        [
            ResearchRecord("u1", role="user", tokens=10),
            ResearchRecord("a1", role="assistant", tokens=10),
            ResearchRecord("tool1", role="tool", tokens=10),
        ],
        keep_recent_tokens=0,
    )

    assert plan.first_kept_record_id == "a1"
    assert plan.summarized_record_ids == ()
    assert plan.turn_prefix_record_ids == ("u1",)
    assert plan.kept_record_ids == ("a1", "tool1")
    assert plan.keep_recent_tokens == 0
