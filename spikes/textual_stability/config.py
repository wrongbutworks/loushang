from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ProfileName = Literal["normal", "high", "extreme"]


@dataclass(frozen=True)
class SpikeProfile:
    name: ProfileName
    assistant_delta_rate: int
    assistant_message_size: int
    tool_count: int
    tool_update_rate: int
    input_submit_interval_ms: int
    history_size: int
    layout_toggle_interval_ms: int
    fault_injection_rate: float


_PROFILES: dict[ProfileName, SpikeProfile] = {
    "normal": SpikeProfile(
        name="normal",
        assistant_delta_rate=10,
        assistant_message_size=16,
        tool_count=3,
        tool_update_rate=10,
        input_submit_interval_ms=1200,
        history_size=60,
        layout_toggle_interval_ms=3000,
        fault_injection_rate=0.0,
    ),
    "high": SpikeProfile(
        name="high",
        assistant_delta_rate=30,
        assistant_message_size=40,
        tool_count=8,
        tool_update_rate=30,
        input_submit_interval_ms=700,
        history_size=240,
        layout_toggle_interval_ms=1500,
        fault_injection_rate=0.01,
    ),
    "extreme": SpikeProfile(
        name="extreme",
        assistant_delta_rate=50,
        assistant_message_size=64,
        tool_count=12,
        tool_update_rate=50,
        input_submit_interval_ms=450,
        history_size=500,
        layout_toggle_interval_ms=1000,
        fault_injection_rate=0.03,
    ),
}


def load_profile(name: str) -> SpikeProfile:
    try:
        return _PROFILES[name]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"unknown profile: {name}") from exc


@dataclass(frozen=True)
class SpikeConfig:
    duration_seconds: int = 180
    profile_name: ProfileName = "high"
    warmup_delay_ms: int = 500
    stall_threshold_ms: int = 2000
    lagging_threshold_ms: int = 1000
    hard_fail_after_ms: int = 4000
    watchdog_poll_interval_ms: int = 250
    heartbeat_interval_ms: int = 200
    use_local_textual: bool = False
    local_textual_checkout: Path = field(default_factory=lambda: Path.home() / "workspace" / "textual")
    seed: int = 0
    profile: SpikeProfile = field(init=False)

    def __post_init__(self) -> None:
        if not 60 <= self.duration_seconds <= 300:
            raise ValueError("duration_seconds must be between 60 and 300")
        if self.warmup_delay_ms < 0:
            raise ValueError("warmup_delay_ms must be >= 0")
        if self.lagging_threshold_ms <= 0:
            raise ValueError("lagging_threshold_ms must be positive")
        if self.stall_threshold_ms <= self.lagging_threshold_ms:
            raise ValueError("stall_threshold_ms must be greater than lagging_threshold_ms")
        if self.hard_fail_after_ms < self.stall_threshold_ms:
            raise ValueError("hard_fail_after_ms must be >= stall_threshold_ms")
        object.__setattr__(self, "profile", load_profile(self.profile_name))

    @property
    def local_textual_src(self) -> Path:
        return self.local_textual_checkout / "src"
