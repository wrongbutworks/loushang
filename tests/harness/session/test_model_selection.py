from __future__ import annotations

import asyncio

from loushang.ai.model import ModelSelection
from loushang.harness.session.model_selection import (
    apply_session_model_selection,
    ensure_usable_session_model,
)


class _Session:
    def __init__(self) -> None:
        self.current: object | None = None
        self.applied: list[object] = []

    async def set_model(self, selection: object) -> None:
        self.applied.append(selection)
        self.current = selection

    def get_model_selection(self) -> object | None:
        return self.current


def test_apply_session_model_selection_uses_product_persistence_callback() -> None:
    session = _Session()
    persisted: list[ModelSelection] = []
    result = asyncio.run(
        apply_session_model_selection(
            session,
            {"provider": "example", "model_id": "model"},
            persist=persisted.append,
        )
    )

    assert result.persisted is True
    assert session.applied == [ModelSelection(provider="example", model_id="model")]
    assert persisted == [ModelSelection(provider="example", model_id="model")]


def test_ensure_usable_session_model_uses_product_candidate_policy() -> None:
    session = _Session()
    candidate = ModelSelection(provider="example", model_id="first")

    result = asyncio.run(
        ensure_usable_session_model(session, candidates=lambda _: [candidate])
    )

    assert result == candidate
    assert session.applied == [candidate]
