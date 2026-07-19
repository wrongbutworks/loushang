from __future__ import annotations

from pathlib import Path

import pytest

from loushang.tui.transcript import UserPromptRecord


def test_coding_ui_perf_probe_reexports_shared_probe_contracts() -> None:
    import loushang.coding.ui.perf_probe as compatibility
    import loushang.harnesstui.testing.performance as shared

    assert compatibility.LongTranscriptRenderMetrics is shared.LongTranscriptRenderMetrics
    assert (
        compatibility.build_synthetic_long_transcript_records
        is shared.build_synthetic_long_transcript_records
    )
    assert (
        compatibility.characterize_long_transcript_rendering
        is shared.characterize_long_transcript_rendering
    )


@pytest.mark.anyio
async def test_coding_performance_loader_adapts_persisted_session_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import loushang.coding.testing.tui.performance as performance

    loaded_paths: list[Path] = []
    projected: list[tuple[object, object]] = []
    resolver = object()

    class FakeManager:
        @classmethod
        async def load(cls, path: Path) -> FakeManager:
            loaded_paths.append(path)
            return cls()

        def build_session_context(self) -> str:
            return "session context"

    def fake_session_history_records(
        session: object,
        *,
        tool_definition_resolver: object,
    ) -> tuple[UserPromptRecord, ...]:
        context = session.get_session_context()  # type: ignore[attr-defined]
        projected.append((context, tool_definition_resolver))
        return (UserPromptRecord("loaded"),)

    monkeypatch.setattr(performance, "SessionManager", FakeManager)
    monkeypatch.setattr(
        performance,
        "session_history_records",
        fake_session_history_records,
    )
    session_path = tmp_path / "nested" / "session.jsonl"

    records = await performance.load_session_history_records(
        session_path,
        tool_definition_resolver=resolver,
    )

    assert loaded_paths == [session_path.resolve()]
    assert projected == [("session context", resolver)]
    assert records == (UserPromptRecord("loaded"),)
