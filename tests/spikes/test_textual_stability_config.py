from __future__ import annotations

import pytest


def test_spike_config_uses_high_profile_defaults() -> None:
    from spikes.textual_stability.config import SpikeConfig, load_profile

    profile = load_profile("high")
    config = SpikeConfig()

    assert config.duration_seconds == 180
    assert config.profile_name == "high"
    assert config.profile == profile
    assert config.stall_threshold_ms == 2000
    assert profile.tool_count == 8
    assert profile.tool_update_rate == 30


@pytest.mark.parametrize("duration", [59, 301])
def test_spike_config_rejects_durations_outside_range(duration: int) -> None:
    from spikes.textual_stability.config import SpikeConfig

    with pytest.raises(ValueError, match="duration_seconds"):
        SpikeConfig(duration_seconds=duration)


def test_load_profile_rejects_unknown_name() -> None:
    from spikes.textual_stability.config import load_profile

    with pytest.raises(ValueError, match="unknown profile"):
        load_profile("oops")


def test_spike_config_rejects_negative_warmup_delay() -> None:
    from spikes.textual_stability.config import SpikeConfig

    with pytest.raises(ValueError, match="warmup_delay_ms"):
        SpikeConfig(warmup_delay_ms=-1)
