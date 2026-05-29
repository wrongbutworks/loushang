from __future__ import annotations


def test_seed_state_builds_expected_history_and_health_counters() -> None:
    from spikes.textual_stability.config import load_profile
    from spikes.textual_stability.state import SpikeState
    from spikes.textual_stability.stressors import StressCoordinator

    state = SpikeState()
    coordinator = StressCoordinator(profile=load_profile("normal"), seed=7)

    coordinator.seed_state(state, base_time=100.0)

    assert len(state.transcript) == coordinator.profile.history_size
    assert state.health.event_count == coordinator.profile.history_size
    assert state.transcript[-1].role in {"user", "assistant"}


def test_assistant_and_tool_ticks_mutate_state_deterministically() -> None:
    from spikes.textual_stability.config import load_profile
    from spikes.textual_stability.state import SpikeState
    from spikes.textual_stability.stressors import StressCoordinator

    state = SpikeState()
    coordinator = StressCoordinator(profile=load_profile("normal"), seed=3)
    coordinator.seed_state(state, base_time=10.0)

    transcript_before = len(state.transcript)
    coordinator.assistant_tick(state, now=11.0)
    coordinator.tool_tick(state, now=11.1)
    coordinator.input_tick(state, now=11.2)

    assert len(state.transcript) >= transcript_before
    assert state.health.last_transcript_at == 11.0
    assert state.health.last_tool_update_at == 11.1
    assert state.input_state.last_submit_at == 11.2
