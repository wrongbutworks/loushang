from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

RecordT = TypeVar("RecordT")
RecordT_contra = TypeVar("RecordT_contra", contravariant=True)
SummaryT = TypeVar("SummaryT")
SummaryT_protocol = TypeVar("SummaryT_protocol")
MissingPreviousSummaryPolicy = Literal["error", "summary_only"]


class ConversationRecordId(Protocol[RecordT_contra]):
    def __call__(self, record: RecordT_contra, /) -> str: ...


class ConversationRecordVisibility(Protocol[RecordT_contra]):
    def __call__(self, record: RecordT_contra, /) -> bool: ...


class ConversationRecordRole(Protocol[RecordT_contra]):
    def __call__(self, record: RecordT_contra, /) -> str | None: ...


class ConversationTokenEstimator(Protocol[RecordT_contra]):
    def __call__(self, record: RecordT_contra, /) -> int: ...


class ConversationContextTokenEstimator(Protocol[RecordT_contra]):
    def __call__(self, records: tuple[RecordT_contra, ...], /) -> int: ...


class ConversationCutGroupBoundary(Protocol[RecordT_contra]):
    """Identify a record that a following cut group must not cross."""

    def __call__(self, record: RecordT_contra, /) -> bool: ...


@dataclass(frozen=True)
class ConversationPreviousSummary(Generic[SummaryT]):
    first_kept_record_id: str
    content: SummaryT
    estimated_tokens: int = 0

    def __post_init__(self) -> None:
        _validate_record_id(self.first_kept_record_id, field="first kept record id")
        _validate_token_count(self.estimated_tokens, field="previous summary tokens")


class ConversationPreviousSummaryResolver(
    Protocol[RecordT_contra, SummaryT_protocol]
):
    def __call__(
        self, record: RecordT_contra, /
    ) -> ConversationPreviousSummary[SummaryT_protocol] | None: ...


@dataclass(frozen=True)
class ConversationRecordPorts(Generic[RecordT, SummaryT]):
    record_id: ConversationRecordId[RecordT]
    is_visible: ConversationRecordVisibility[RecordT]
    role: ConversationRecordRole[RecordT]
    estimate_tokens: ConversationTokenEstimator[RecordT]
    estimate_context_tokens: ConversationContextTokenEstimator[RecordT] | None = None
    separates_cut_group: ConversationCutGroupBoundary[RecordT] | None = None
    previous_summary: ConversationPreviousSummaryResolver[RecordT, SummaryT] | None = (
        None
    )


@dataclass(frozen=True)
class ConversationTurn(Generic[RecordT]):
    records: tuple[RecordT, ...]
    record_ids: tuple[str, ...]
    roles: tuple[str | None, ...]
    estimated_tokens: int

    def __post_init__(self) -> None:
        if not self.records:
            raise ValueError("conversation turn must contain at least one record")
        if len(self.records) != len(self.record_ids) or len(self.records) != len(
            self.roles
        ):
            raise ValueError("conversation turn facts must have matching lengths")
        _validate_token_count(self.estimated_tokens, field="turn tokens")


@dataclass(frozen=True)
class ConversationSummaryBoundary(Generic[SummaryT]):
    record_id: str
    first_kept_record_id: str
    content: SummaryT
    estimated_tokens: int

    def __post_init__(self) -> None:
        _validate_record_id(self.record_id, field="summary record id")
        _validate_record_id(self.first_kept_record_id, field="first kept record id")
        _validate_token_count(self.estimated_tokens, field="previous summary tokens")


@dataclass(frozen=True)
class ConversationCompactionPlan(Generic[RecordT, SummaryT]):
    previous_summary: ConversationSummaryBoundary[SummaryT] | None
    first_kept_record_id: str
    summarized_records: tuple[RecordT, ...]
    turn_prefix_records: tuple[RecordT, ...]
    kept_records: tuple[RecordT, ...]
    summarized_record_ids: tuple[str, ...]
    turn_prefix_record_ids: tuple[str, ...]
    kept_record_ids: tuple[str, ...]
    turns: tuple[ConversationTurn[RecordT], ...]
    is_split_turn: bool
    estimated_record_tokens: int
    previous_summary_tokens: int
    tokens_before: int
    accounted_tokens_before: int
    summarized_tokens: int
    turn_prefix_tokens: int
    kept_tokens: int
    keep_recent_tokens: int

    def __post_init__(self) -> None:
        _validate_record_id(self.first_kept_record_id, field="first kept record id")
        for field_name, value in (
            ("estimated record tokens", self.estimated_record_tokens),
            ("previous summary tokens", self.previous_summary_tokens),
            ("tokens before", self.tokens_before),
            ("accounted tokens before", self.accounted_tokens_before),
            ("summarized tokens", self.summarized_tokens),
            ("turn prefix tokens", self.turn_prefix_tokens),
            ("kept tokens", self.kept_tokens),
            ("keep recent tokens", self.keep_recent_tokens),
        ):
            _validate_token_count(value, field=field_name)
        if self.accounted_tokens_before != (
            self.tokens_before + self.previous_summary_tokens
        ):
            raise ValueError(
                "accounted tokens before must include context and previous summary tokens"
            )


class ConversationCompactionPlanner(Generic[RecordT, SummaryT]):
    """Plan conversation reduction without knowing product record or model types."""

    def __init__(
        self,
        ports: ConversationRecordPorts[RecordT, SummaryT],
        *,
        turn_start_roles: frozenset[str] = frozenset({"user"}),
        non_cut_roles: frozenset[str] = frozenset(
            {"tool", "tool_result", "toolResult"}
        ),
        missing_previous_summary: MissingPreviousSummaryPolicy = "error",
    ) -> None:
        if not turn_start_roles:
            raise ValueError("turn start roles must not be empty")
        if missing_previous_summary not in {"error", "summary_only"}:
            raise ValueError(
                "missing previous summary policy must be 'error' or 'summary_only'"
            )
        self._ports = ports
        self._turn_start_roles = frozenset(turn_start_roles)
        self._non_cut_roles = frozenset(non_cut_roles)
        self._missing_previous_summary = missing_previous_summary

    def group_turns(
        self, records: tuple[RecordT, ...] | list[RecordT]
    ) -> tuple[ConversationTurn[RecordT], ...]:
        facts = self._facts(tuple(records))
        return self._group_turns(facts)

    def plan(
        self,
        records: tuple[RecordT, ...] | list[RecordT],
        *,
        keep_recent_tokens: int,
    ) -> ConversationCompactionPlan[RecordT, SummaryT]:
        _validate_token_count(keep_recent_tokens, field="keep recent tokens")
        keep_tokens = keep_recent_tokens
        all_records = tuple(records)
        all_ids = self._validated_record_ids(all_records)
        previous_summary, boundary_start = self._previous_summary_boundary(
            all_records, all_ids
        )
        facts = self._facts(
            all_records[boundary_start:],
            source_offset=boundary_start,
        )
        if not facts:
            raise ValueError(
                "conversation compaction requires at least one visible record"
            )

        cut_index = self._find_cut_index(facts, keep_tokens)
        cut_source_index = facts[cut_index].source_index
        first_kept_source_index = self._expand_cut_group(
            all_records,
            boundary_start=boundary_start,
            cut_source_index=cut_source_index,
        )
        effective_cut_index = next(
            index
            for index, fact in enumerate(facts)
            if fact.source_index >= first_kept_source_index
        )
        turn_start_index = self._find_turn_start_index(facts, effective_cut_index)
        is_split_turn = (
            turn_start_index is not None
            and facts[effective_cut_index].role not in self._turn_start_roles
        )
        history_end = turn_start_index if is_split_turn else effective_cut_index

        summarized = facts[:history_end]
        turn_prefix = (
            facts[history_end:effective_cut_index] if is_split_turn else ()
        )
        kept = tuple(
            fact for fact in facts if fact.source_index >= first_kept_source_index
        )
        previous_tokens = (
            previous_summary.estimated_tokens if previous_summary is not None else 0
        )
        estimated_record_tokens = sum(fact.estimated_tokens for fact in facts)
        context_records = tuple(fact.record for fact in facts)
        context_estimator = self._ports.estimate_context_tokens
        tokens_before = (
            context_estimator(context_records)
            if context_estimator is not None
            else estimated_record_tokens
        )
        _validate_token_count(tokens_before, field="context tokens before")

        return ConversationCompactionPlan(
            previous_summary=previous_summary,
            first_kept_record_id=all_ids[first_kept_source_index],
            summarized_records=tuple(fact.record for fact in summarized),
            turn_prefix_records=tuple(fact.record for fact in turn_prefix),
            kept_records=tuple(fact.record for fact in kept),
            summarized_record_ids=tuple(fact.record_id for fact in summarized),
            turn_prefix_record_ids=tuple(fact.record_id for fact in turn_prefix),
            kept_record_ids=tuple(fact.record_id for fact in kept),
            turns=self._group_turns(facts),
            is_split_turn=is_split_turn,
            estimated_record_tokens=estimated_record_tokens,
            previous_summary_tokens=previous_tokens,
            tokens_before=tokens_before,
            accounted_tokens_before=tokens_before + previous_tokens,
            summarized_tokens=sum(fact.estimated_tokens for fact in summarized),
            turn_prefix_tokens=sum(fact.estimated_tokens for fact in turn_prefix),
            kept_tokens=sum(fact.estimated_tokens for fact in kept),
            keep_recent_tokens=keep_tokens,
        )

    def _validated_record_ids(self, records: tuple[RecordT, ...]) -> tuple[str, ...]:
        record_ids: list[str] = []
        seen: set[str] = set()
        for record in records:
            record_id = self._ports.record_id(record)
            _validate_record_id(record_id, field="conversation record id")
            if record_id in seen:
                raise ValueError(f"duplicate conversation record id: {record_id}")
            seen.add(record_id)
            record_ids.append(record_id)
        return tuple(record_ids)

    def _previous_summary_boundary(
        self,
        records: tuple[RecordT, ...],
        record_ids: tuple[str, ...],
    ) -> tuple[ConversationSummaryBoundary[SummaryT] | None, int]:
        resolver = self._ports.previous_summary
        if resolver is None:
            return None, 0

        for index in range(len(records) - 1, -1, -1):
            summary = resolver(records[index])
            if summary is None:
                continue
            boundary = ConversationSummaryBoundary(
                record_id=record_ids[index],
                first_kept_record_id=summary.first_kept_record_id,
                content=summary.content,
                estimated_tokens=summary.estimated_tokens,
            )
            try:
                first_kept_index = record_ids.index(
                    summary.first_kept_record_id,
                    0,
                    index,
                )
            except ValueError:
                if self._missing_previous_summary == "error":
                    raise ValueError(
                        "conversation previous summary refers to missing or future "
                        f"record {summary.first_kept_record_id}"
                    ) from None
                first_kept_index = index + 1
            return boundary, first_kept_index
        return None, 0

    def _facts(
        self,
        records: tuple[RecordT, ...],
        *,
        source_offset: int = 0,
    ) -> tuple[_RecordFact[RecordT], ...]:
        facts: list[_RecordFact[RecordT]] = []
        for source_index, record in enumerate(records, start=source_offset):
            if not self._ports.is_visible(record):
                continue
            record_id = self._ports.record_id(record)
            _validate_record_id(record_id, field="conversation record id")
            tokens = self._ports.estimate_tokens(record)
            _validate_token_count(tokens, field=f"tokens for record {record_id}")
            role = self._ports.role(record)
            if role is not None and (not isinstance(role, str) or not role.strip()):
                raise ValueError(
                    f"role for visible record {record_id} must be a non-empty string or None"
                )
            facts.append(
                _RecordFact(
                    record=record,
                    record_id=record_id,
                    role=role,
                    estimated_tokens=tokens,
                    source_index=source_index,
                )
            )
        return tuple(facts)

    def _expand_cut_group(
        self,
        records: tuple[RecordT, ...],
        *,
        boundary_start: int,
        cut_source_index: int,
    ) -> int:
        separates_cut_group = self._ports.separates_cut_group
        if separates_cut_group is None:
            return cut_source_index
        first_kept_index = cut_source_index
        while first_kept_index > boundary_start:
            previous = records[first_kept_index - 1]
            if separates_cut_group(previous):
                break
            first_kept_index -= 1
        return first_kept_index

    def _find_cut_index(
        self, facts: tuple[_RecordFact[RecordT], ...], keep_recent_tokens: int
    ) -> int:
        cut_points = tuple(
            index
            for index, fact in enumerate(facts)
            if fact.role not in self._non_cut_roles
        )
        if not cut_points:
            raise ValueError("conversation has no eligible compaction cut point")

        accumulated_tokens = 0
        scan_index: int | None = None
        for index in range(len(facts) - 1, -1, -1):
            accumulated_tokens += facts[index].estimated_tokens
            if accumulated_tokens >= keep_recent_tokens:
                scan_index = index
                break
        if scan_index is None:
            return cut_points[0]

        for candidate in cut_points:
            if candidate >= scan_index:
                return candidate
        return cut_points[-1]

    def _find_turn_start_index(
        self, facts: tuple[_RecordFact[RecordT], ...], cut_index: int
    ) -> int | None:
        if facts[cut_index].role in self._turn_start_roles:
            return cut_index
        for index in range(cut_index, -1, -1):
            if facts[index].role in self._turn_start_roles:
                return index
        return None

    def _group_turns(
        self, facts: tuple[_RecordFact[RecordT], ...]
    ) -> tuple[ConversationTurn[RecordT], ...]:
        groups: list[list[_RecordFact[RecordT]]] = []
        for fact in facts:
            if fact.role in self._turn_start_roles or not groups:
                groups.append([])
            groups[-1].append(fact)
        return tuple(
            ConversationTurn(
                records=tuple(fact.record for fact in group),
                record_ids=tuple(fact.record_id for fact in group),
                roles=tuple(fact.role for fact in group),
                estimated_tokens=sum(fact.estimated_tokens for fact in group),
            )
            for group in groups
        )


@dataclass(frozen=True)
class _RecordFact(Generic[RecordT]):
    record: RecordT
    record_id: str
    role: str | None
    estimated_tokens: int
    source_index: int


def _validate_record_id(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _validate_token_count(value: object, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")


__all__ = [
    "ConversationCompactionPlan",
    "ConversationCompactionPlanner",
    "ConversationContextTokenEstimator",
    "ConversationCutGroupBoundary",
    "ConversationPreviousSummary",
    "ConversationPreviousSummaryResolver",
    "ConversationRecordId",
    "ConversationRecordPorts",
    "ConversationRecordRole",
    "ConversationRecordVisibility",
    "ConversationSummaryBoundary",
    "ConversationTokenEstimator",
    "ConversationTurn",
    "MissingPreviousSummaryPolicy",
]
