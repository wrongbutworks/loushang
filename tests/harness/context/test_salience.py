from __future__ import annotations

from loushang.harness.context import (
    ContextBundle,
    ContextItem,
    ContextSalienceRanker,
    SalienceSignal,
    WeightedSalienceScorer,
)


def test_weighted_salience_ranking_is_explainable_and_non_mutating() -> None:
    bundle = ContextBundle(
        items=(
            ContextItem(
                item_id="question",
                kind="question",
                content="What caused the margin change?",
                estimated_tokens=9,
                pinned=True,
            ),
            ContextItem(
                item_id="old-claim",
                kind="claim",
                content="Margins fell.",
                estimated_tokens=4,
                priority=1,
                metadata={"confidence": 0.4},
            ),
            ContextItem(
                item_id="new-evidence",
                kind="evidence",
                content="Input costs rose 18%.",
                estimated_tokens=6,
                metadata={"confidence": 0.9},
            ),
        )
    )
    scorer = WeightedSalienceScorer[str](
        recency_weight=2,
        priority_weight=1,
        kind_weights={"evidence": 2},
        metadata_weights={"confidence": 3},
    )

    ranking = ContextSalienceRanker().rank(bundle, scorer)

    assert ranking.ranked_item_ids == (
        "question",
        "new-evidence",
        "old-claim",
    )
    evidence = ranking.get("new-evidence")
    assert evidence is not None
    assert evidence.score == 6.7
    assert tuple(signal.name for signal in evidence.signals) == (
        "recency",
        "priority",
        "kind:evidence",
        "metadata:confidence",
    )
    assert tuple(item.item_id for item in bundle.items) == (
        "question",
        "old-claim",
        "new-evidence",
    )


def test_product_scorer_can_add_domain_signals_without_harness_content_rules() -> None:
    class CitationScorer:
        def signals(self, item, *, position: int, total: int):
            del position, total
            return (
                SalienceSignal(
                    name="verified-citations",
                    value=item.content["verified_citations"],
                    weight=2,
                ),
            )

    bundle = ContextBundle(
        items=(
            ContextItem(
                item_id="claim-a",
                kind="claim",
                content={"verified_citations": 1},
                estimated_tokens=4,
            ),
            ContextItem(
                item_id="claim-b",
                kind="claim",
                content={"verified_citations": 3},
                estimated_tokens=4,
            ),
        )
    )

    ranking = ContextSalienceRanker().rank(bundle, CitationScorer())

    assert ranking.ranked_item_ids == ("claim-b", "claim-a")
