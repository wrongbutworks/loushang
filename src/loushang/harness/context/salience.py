from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Generic, Protocol, TypeVar

from loushang.harness.context.types import ContextBundle, ContextItem

T = TypeVar("T")


@dataclass(frozen=True)
class SalienceSignal:
    name: str
    value: float
    weight: float = 1.0
    reason: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("salience signal name must not be empty")
        value = float(self.value)
        weight = float(self.weight)
        if not isfinite(value) or not isfinite(weight):
            raise ValueError("salience signal value and weight must be finite")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "weight", weight)

    @property
    def contribution(self) -> float:
        return self.value * self.weight


@dataclass(frozen=True)
class SalienceAssessment:
    item_id: str
    score: float
    signals: tuple[SalienceSignal, ...] = ()
    pinned: bool = False
    source_position: int = 0


@dataclass(frozen=True)
class SalienceRanking:
    assessments: tuple[SalienceAssessment, ...]

    @property
    def ranked_item_ids(self) -> tuple[str, ...]:
        return tuple(assessment.item_id for assessment in self.assessments)

    def get(self, item_id: str) -> SalienceAssessment | None:
        return next(
            (
                assessment
                for assessment in self.assessments
                if assessment.item_id == item_id
            ),
            None,
        )


class SalienceScorer(Protocol, Generic[T]):
    def signals(
        self,
        item: ContextItem[T],
        *,
        position: int,
        total: int,
    ) -> Sequence[SalienceSignal]: ...


@dataclass(frozen=True)
class WeightedSalienceScorer(Generic[T]):
    """Score only neutral item structure using Product-supplied weights."""

    recency_weight: float = 0.0
    priority_weight: float = 1.0
    kind_weights: Mapping[str, float] = field(default_factory=dict)
    metadata_weights: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        weights = (
            self.recency_weight,
            self.priority_weight,
            *self.kind_weights.values(),
            *self.metadata_weights.values(),
        )
        if any(not isfinite(float(weight)) for weight in weights):
            raise ValueError("salience weights must be finite")
        object.__setattr__(self, "recency_weight", float(self.recency_weight))
        object.__setattr__(self, "priority_weight", float(self.priority_weight))
        object.__setattr__(
            self,
            "kind_weights",
            {key: float(weight) for key, weight in self.kind_weights.items()},
        )
        object.__setattr__(
            self,
            "metadata_weights",
            {
                key: float(weight)
                for key, weight in self.metadata_weights.items()
            },
        )

    def signals(
        self,
        item: ContextItem[T],
        *,
        position: int,
        total: int,
    ) -> tuple[SalienceSignal, ...]:
        signals: list[SalienceSignal] = []
        if self.recency_weight:
            recency = 1.0 if total <= 1 else position / (total - 1)
            signals.append(
                SalienceSignal(
                    name="recency",
                    value=recency,
                    weight=self.recency_weight,
                )
            )
        if self.priority_weight:
            signals.append(
                SalienceSignal(
                    name="priority",
                    value=item.priority,
                    weight=self.priority_weight,
                )
            )
        kind_weight = self.kind_weights.get(item.kind)
        if kind_weight:
            signals.append(
                SalienceSignal(
                    name=f"kind:{item.kind}",
                    value=1.0,
                    weight=kind_weight,
                )
            )
        for key, weight in self.metadata_weights.items():
            value = item.metadata.get(key)
            if isinstance(value, bool):
                numeric_value = float(value)
            elif isinstance(value, int | float):
                numeric_value = float(value)
            else:
                continue
            signals.append(
                SalienceSignal(
                    name=f"metadata:{key}",
                    value=numeric_value,
                    weight=weight,
                )
            )
        return tuple(signals)


class ContextSalienceRanker:
    def rank(
        self,
        bundle: ContextBundle[T],
        scorer: SalienceScorer[T],
    ) -> SalienceRanking:
        assessments = []
        total = len(bundle.items)
        for position, item in enumerate(bundle.items):
            signals = tuple(scorer.signals(item, position=position, total=total))
            assessments.append(
                SalienceAssessment(
                    item_id=item.item_id,
                    score=sum(signal.contribution for signal in signals),
                    signals=signals,
                    pinned=item.pinned,
                    source_position=position,
                )
            )
        assessments.sort(
            key=lambda assessment: (
                not assessment.pinned,
                -assessment.score,
                assessment.source_position,
            )
        )
        return SalienceRanking(tuple(assessments))


__all__ = [
    "ContextSalienceRanker",
    "SalienceAssessment",
    "SalienceRanking",
    "SalienceScorer",
    "SalienceSignal",
    "WeightedSalienceScorer",
]
