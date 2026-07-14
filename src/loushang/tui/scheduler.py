from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

RenderRequestKind = Literal["input", "stream", "timer", "product", "resize"]


class AnimationFrameSource(Protocol):
    def next_frame_due_ms(self, *, after_ms: int) -> int | None: ...


@dataclass(frozen=True, slots=True)
class RenderSchedulerConfig:
    min_render_interval_ms: int = 16
    max_coalescing_delay_ms: int = 50
    input_echo_deadline_ms: int = 16
    stream_min_render_interval_ms: int = 50

    def __post_init__(self) -> None:
        if self.min_render_interval_ms < 0:
            raise ValueError("min_render_interval_ms must be non-negative")
        if self.max_coalescing_delay_ms < 0:
            raise ValueError("max_coalescing_delay_ms must be non-negative")
        if self.input_echo_deadline_ms < 0:
            raise ValueError("input_echo_deadline_ms must be non-negative")
        if self.stream_min_render_interval_ms < 0:
            raise ValueError("stream_min_render_interval_ms must be non-negative")


@dataclass(frozen=True, slots=True)
class RenderScheduleDecision:
    render_now: bool
    delay_ms: int
    coalesced: bool


@dataclass(slots=True)
class RenderScheduler:
    config: RenderSchedulerConfig = RenderSchedulerConfig()
    last_rendered_at_ms: int | None = None

    def mark_rendered(self, *, now_ms: int) -> None:
        self.last_rendered_at_ms = now_ms

    def request_render(self, kind: RenderRequestKind, *, now_ms: int) -> RenderScheduleDecision:
        if kind in ("input", "resize") or self.last_rendered_at_ms is None:
            return RenderScheduleDecision(render_now=True, delay_ms=0, coalesced=False)

        elapsed_ms = max(0, now_ms - self.last_rendered_at_ms)
        min_interval_ms = (
            self.config.stream_min_render_interval_ms
            if kind == "stream"
            else self.config.min_render_interval_ms
        )
        if elapsed_ms >= min_interval_ms:
            return RenderScheduleDecision(render_now=True, delay_ms=0, coalesced=False)

        remaining_ms = min_interval_ms - elapsed_ms
        delay_ms = (
            remaining_ms
            if kind == "stream"
            else min(remaining_ms, self.config.max_coalescing_delay_ms)
        )
        return RenderScheduleDecision(render_now=False, delay_ms=delay_ms, coalesced=True)

    def request_animation_frame(self, source: AnimationFrameSource, *, now_ms: int) -> RenderScheduleDecision:
        if self.last_rendered_at_ms is None:
            return self.request_render("timer", now_ms=now_ms)
        due_ms = source.next_frame_due_ms(after_ms=self.last_rendered_at_ms)
        if due_ms is None:
            return RenderScheduleDecision(render_now=False, delay_ms=0, coalesced=False)
        if due_ms <= now_ms:
            return self.request_render("timer", now_ms=now_ms)
        return RenderScheduleDecision(render_now=False, delay_ms=due_ms - now_ms, coalesced=True)
