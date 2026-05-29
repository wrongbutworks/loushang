from __future__ import annotations

import builtins
from pathlib import Path

import pytest


def test_ensure_textual_importable_reports_missing_dependency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from spikes.textual_stability.app import ensure_textual_importable
    from spikes.textual_stability.config import SpikeConfig

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "textual":
            raise ModuleNotFoundError("No module named 'rich'", name="rich")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    config = SpikeConfig(use_local_textual=True, local_textual_checkout=tmp_path)

    with pytest.raises(RuntimeError, match="Missing module: rich"):
        ensure_textual_importable(config)


def test_build_app_does_not_override_textual_internal_shutdown() -> None:
    from spikes.textual_stability.app import build_app
    from spikes.textual_stability.config import SpikeConfig

    app_class = build_app(SpikeConfig())

    assert "_shutdown" not in app_class.__dict__


def test_app_reports_warmup_placeholders_before_stress_start() -> None:
    pytest.importorskip("textual")

    from spikes.textual_stability.app import build_app
    from spikes.textual_stability.config import SpikeConfig

    app_class = build_app(SpikeConfig(duration_seconds=60, profile_name="normal", warmup_delay_ms=200))
    app = app_class()
    app.started_at = 100.0
    app.heartbeat.record_heartbeat(100.0)

    assert app.stress_started is False
    assert app.state.transcript == []
    assert app._transcript_text() == "warming up transcript…"
    assert app._tools_text() == "warming up tool pane…"
    assert "phase=warming_up" in app._status_text(now=100.05)
    assert "heartbeat=1" in app._status_text(now=100.05)


def test_app_prime_stress_state_seeds_initial_history_chunk_without_mount() -> None:
    pytest.importorskip("textual")

    from spikes.textual_stability.app import build_app
    from spikes.textual_stability.config import SpikeConfig

    app_class = build_app(SpikeConfig(duration_seconds=60, profile_name="normal", warmup_delay_ms=200))
    app = app_class()
    app.started_at = 100.0
    app.heartbeat.record_heartbeat(100.0)

    app._prime_stress_state(now=100.2)

    assert app.stress_started is True
    assert app.stress_started_at == 100.2
    assert app.seeded_history_entries == min(app.SEED_CHUNK_SIZE, app.config.profile.history_size)
    assert len(app.state.transcript) == app.seeded_history_entries
    assert app.state.input_state.buffer == "auto-input primed"
    assert "warming up" not in app._transcript_text().lower()
    assert "phase=running" in app._status_text(now=100.3)


def test_app_can_seed_remaining_history_in_chunks() -> None:
    pytest.importorskip("textual")

    from spikes.textual_stability.app import build_app
    from spikes.textual_stability.config import SpikeConfig

    app_class = build_app(SpikeConfig(duration_seconds=60, profile_name="normal", warmup_delay_ms=200))
    app = app_class()

    app._prime_stress_state(now=100.2)
    while app.seeded_history_entries < app.config.profile.history_size:
        assert app._seed_next_history_chunk() is True

    assert app.seeded_history_entries == app.config.profile.history_size
    assert len(app.state.transcript) == app.config.profile.history_size
    assert app._seed_next_history_chunk() is False
