from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _ResearchRecord:
    event_id: str
    parent_event_id: str | None
    stage: str
    content: str


def _research_repository():
    from loushang.harness.conversation import ConversationRepository

    records = (
        _ResearchRecord("question", None, "question", "How is demand changing?"),
        _ResearchRecord("filings", "question", "evidence", "Read filings"),
        _ResearchRecord("filing-note", "filings", "note", "Demand is rising"),
        _ResearchRecord("interviews", "question", "evidence", "Run interviews"),
        _ResearchRecord(
            "interview-note",
            "interviews",
            "note",
            "Demand is regional",
        ),
    )
    return ConversationRepository.create(
        header={"id": "research-1"},
        records=records,
        record_id=lambda record: record.event_id,
        parent_id=lambda record: record.parent_event_id,
    )


def test_research_branches_project_delta_after_lowest_common_ancestor() -> None:
    repository = _research_repository()

    ancestor = repository.lowest_common_ancestor("filing-note", "interview-note")
    delta = repository.branch_delta("filing-note", "interview-note")

    assert ancestor is not None
    assert ancestor.event_id == "question"
    assert delta.common_ancestor_id == "question"
    assert [record.event_id for record in delta.divergent_records] == [
        "filings",
        "filing-note",
    ]


def test_research_branch_delta_is_directional_and_empty_for_an_ancestor() -> None:
    repository = _research_repository()

    reverse = repository.branch_delta("interview-note", "filing-note")
    ancestor = repository.branch_delta("filings", "filing-note")

    assert [record.event_id for record in reverse.divergent_records] == [
        "interviews",
        "interview-note",
    ]
    assert ancestor.common_ancestor_id == "filings"
    assert ancestor.divergent_records == ()
