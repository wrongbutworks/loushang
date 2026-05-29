from __future__ import annotations

import random
from dataclasses import dataclass, field

from spikes.textual_stability.config import SpikeProfile
from spikes.textual_stability.state import SpikeState


_WORDS = (
    "alpha",
    "beta",
    "gamma",
    "delta",
    "stream",
    "watchdog",
    "tool",
    "pane",
    "input",
    "render",
)


@dataclass
class StressCoordinator:
    profile: SpikeProfile
    seed: int = 0
    _rng: random.Random = field(init=False, repr=False)
    _assistant_remaining: int = field(init=False, default=0)
    _prompt_seq: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def seed_state(self, state: SpikeState, *, base_time: float) -> None:
        self.seed_state_chunk(state, base_time=base_time, start_index=0, count=self.profile.history_size)

    def seed_state_chunk(self, state: SpikeState, *, base_time: float, start_index: int, count: int) -> None:
        for offset in range(count):
            index = start_index + offset
            role = "user" if index % 2 == 0 else "assistant"
            state.append_entry(role, f"{role} seeded message {index}", created_at=base_time + index * 0.001)

    def assistant_tick(self, state: SpikeState, *, now: float) -> None:
        token = self._random_token()
        if self._assistant_remaining <= 0:
            self._assistant_remaining = self.profile.assistant_message_size - 1
            finish = self.profile.assistant_message_size <= 1
        else:
            self._assistant_remaining -= 1
            finish = self._assistant_remaining == 0
        state.append_assistant_delta(token, now=now, finish=finish)

    def tool_tick(self, state: SpikeState, *, now: float) -> None:
        slot = self._rng.randint(1, self.profile.tool_count)
        tool_id = f"tool-{slot}"
        existing = state.tools.get(tool_id)
        if existing is None or existing.phase in {"done", "error"}:
            progress = self._rng.randint(0, 20)
            phase = "running"
        else:
            progress = min(100, existing.progress + self._rng.randint(8, 25))
            if self.profile.fault_injection_rate and self._rng.random() < self.profile.fault_injection_rate:
                phase = "error"
            else:
                phase = "done" if progress >= 100 else "running"
        state.upsert_tool(tool_id, title=f"Tool {slot}", phase=phase, progress=progress, now=now)

    def input_tick(self, state: SpikeState, *, now: float) -> None:
        if state.input_state.submitting:
            state.ack_input(now=now)
            return
        self._prompt_seq += 1
        state.submit_input(f"auto prompt {self._prompt_seq}: {self._random_token().strip()}", now=now)

    def _random_token(self) -> str:
        return self._rng.choice(_WORDS) + " "
