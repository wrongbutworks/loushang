from __future__ import annotations

from loushang.tui import Loader, RenderScheduler, RenderSchedulerConfig


def test_scheduler_records_pi_style_tuning_parameters() -> None:
    config = RenderSchedulerConfig()

    assert config.min_render_interval_ms == 16
    assert config.max_coalescing_delay_ms == 50
    assert config.input_echo_deadline_ms == 16


def test_scheduler_coalesces_stream_ticks_but_keeps_input_immediate() -> None:
    scheduler = RenderScheduler(RenderSchedulerConfig(min_render_interval_ms=16, max_coalescing_delay_ms=50))
    scheduler.mark_rendered(now_ms=100)

    stream_decision = scheduler.request_render("stream", now_ms=105)
    input_decision = scheduler.request_render("input", now_ms=106)

    assert stream_decision.render_now is False
    assert stream_decision.delay_ms == 11
    assert stream_decision.coalesced is True
    assert input_decision.render_now is True
    assert input_decision.delay_ms == 0
    assert input_decision.coalesced is False


def test_scheduler_caps_stream_delay_at_max_coalescing_delay() -> None:
    scheduler = RenderScheduler(RenderSchedulerConfig(min_render_interval_ms=100, max_coalescing_delay_ms=40))
    scheduler.mark_rendered(now_ms=10)

    decision = scheduler.request_render("timer", now_ms=20)

    assert decision.render_now is False
    assert decision.delay_ms == 40
    assert decision.coalesced is True


def test_scheduler_requests_loader_animation_render_at_next_due_frame() -> None:
    now = [0]
    loader = Loader(message="Loading", frames=("a", "b"), interval_ms=80, now_ms=lambda: now[0])
    scheduler = RenderScheduler()
    scheduler.mark_rendered(now_ms=0)

    early = scheduler.request_animation_frame(loader, now_ms=40)
    due = scheduler.request_animation_frame(loader, now_ms=80)

    assert early.render_now is False
    assert early.delay_ms == 40
    assert early.coalesced is True
    assert due.render_now is True
    assert due.delay_ms == 0
    assert due.coalesced is False


def test_scheduler_ignores_non_animating_loader() -> None:
    loader = Loader(message="Loading", frames=("a",))
    scheduler = RenderScheduler()
    scheduler.mark_rendered(now_ms=0)

    decision = scheduler.request_animation_frame(loader, now_ms=1_000)

    assert decision.render_now is False
    assert decision.delay_ms == 0
    assert decision.coalesced is False
