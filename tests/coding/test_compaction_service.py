from __future__ import annotations

import asyncio


def test_compaction_coordinator_compacts_session_and_tracks_status() -> None:
    from loushang.coding.compaction import CompactionCoordinator, CompactionResult

    class FakeSession:
        def __init__(self) -> None:
            self.compact_calls: list[str | None] = []

        async def compact_session(self, custom_instructions: str | None = None) -> CompactionResult:
            self.compact_calls.append(custom_instructions)
            return CompactionResult(
                summary="summary",
                first_kept_entry_id="entry-1",
                tokens_before=42,
            )

    async def scenario() -> None:
        coordinator = CompactionCoordinator()
        session = FakeSession()

        result = await coordinator.compact_session(session, custom_instructions="keep decisions")

        assert result.summary == "summary"
        assert session.compact_calls == ["keep decisions"]
        status = coordinator.get_status()
        assert status.is_compacting is False
        assert status.last_reason == "manual"
        assert status.last_result == result
        assert status.last_error is None

    asyncio.run(scenario())


def test_compaction_coordinator_maybe_compacts_after_turn() -> None:
    from loushang.coding.compaction import CompactionCoordinator, CompactionResult

    class FakeSession:
        def __init__(self) -> None:
            self.messages: list[object] = []

        async def maybe_compact_after_turn(self, assistant_message: object) -> CompactionResult | None:
            self.messages.append(assistant_message)
            return CompactionResult(
                summary="threshold summary",
                first_kept_entry_id="entry-2",
                tokens_before=99,
            )

    async def scenario() -> None:
        coordinator = CompactionCoordinator()
        session = FakeSession()
        message = object()

        result = await coordinator.maybe_compact_after_turn(session, message)

        assert result is not None
        assert result.summary == "threshold summary"
        assert session.messages == [message]
        status = coordinator.get_status()
        assert status.is_compacting is False
        assert status.last_reason == "threshold"
        assert status.last_result == result

    asyncio.run(scenario())


def test_compaction_coordinator_records_errors() -> None:
    import pytest

    from loushang.coding.compaction import CompactionCoordinator

    class FakeSession:
        async def compact_session(self, custom_instructions: str | None = None):
            del custom_instructions
            raise RuntimeError("boom")

    async def scenario() -> None:
        coordinator = CompactionCoordinator()

        with pytest.raises(RuntimeError, match="boom"):
            await coordinator.compact_session(FakeSession())

        status = coordinator.get_status()
        assert status.is_compacting is False
        assert status.last_reason == "manual"
        assert status.last_error == "boom"

    asyncio.run(scenario())
