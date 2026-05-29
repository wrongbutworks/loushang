from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from spikes.textual_stability.config import SpikeConfig
from spikes.textual_stability.state import SpikeState
from spikes.textual_stability.stressors import StressCoordinator
from spikes.textual_stability.watchdog import HeartbeatState, Watchdog, WatchdogSnapshot, WatchdogThread


def parse_args(argv: list[str] | None = None) -> SpikeConfig:
    parser = argparse.ArgumentParser(description="Timed Textual stability spike.")
    parser.add_argument("--duration-seconds", type=int, default=180)
    parser.add_argument("--profile", choices=("normal", "high", "extreme"), default="high")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--use-local-textual", action="store_true")
    parser.add_argument("--local-textual-checkout", type=Path, default=Path.home() / "workspace" / "textual")
    args = parser.parse_args(argv)
    return SpikeConfig(
        duration_seconds=args.duration_seconds,
        profile_name=args.profile,
        seed=args.seed,
        use_local_textual=args.use_local_textual,
        local_textual_checkout=args.local_textual_checkout,
    )


def ensure_textual_importable(config: SpikeConfig) -> None:
    if config.use_local_textual:
        sys.path.insert(0, str(config.local_textual_src))

    try:
        __import__("textual")
    except ModuleNotFoundError as exc:
        location = config.local_textual_src if config.use_local_textual else "the active environment"
        missing = f" Missing module: {exc.name}." if exc.name else ""
        raise RuntimeError(
            "Textual is not importable. "
            f"Looked in {location!s}. "
            f"Install Textual and its runtime dependencies.{missing}"
        ) from exc


def build_app(config: SpikeConfig):
    ensure_textual_importable(config)

    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Footer, Header, Static, TextArea

    class TextualStabilityApp(App[None]):
        SEED_CHUNK_SIZE = 40

        CSS = """
        Screen {
            layout: vertical;
        }

        #body {
            height: 1fr;
            layout: horizontal;
        }

        #main-pane {
            width: 3fr;
            border: round $accent;
        }

        #tool-pane {
            width: 2fr;
            border: round $primary;
        }

        #transcript-scroll, #tool-scroll {
            height: 1fr;
        }

        #input-pane {
            height: 8;
            border-top: solid $boost;
        }

        #status {
            height: auto;
            border-top: solid $panel;
            padding: 0 1;
        }
        """

        BINDINGS = [("q", "quit", "Quit")]

        def __init__(self) -> None:
            super().__init__()
            self.config = config
            self.state = SpikeState()
            self.heartbeat = HeartbeatState()
            self.watchdog = Watchdog(
                lagging_threshold_ms=config.lagging_threshold_ms,
                stall_threshold_ms=config.stall_threshold_ms,
            )
            self.coordinator = StressCoordinator(profile=config.profile, seed=config.seed)
            self.started_at = 0.0
            self.completed = False
            self.failure_reason: str | None = None
            self.latest_watchdog_snapshot: WatchdogSnapshot | None = None
            self.layout_show_tools = True
            self.watchdog_thread: WatchdogThread | None = None
            self.stress_started = False
            self.active_stressors_started = False
            self.stress_started_at: float | None = None
            self.seeded_history_entries = 0

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="body"):
                with Vertical(id="main-pane"):
                    with VerticalScroll(id="transcript-scroll"):
                        yield Static("warming up transcript…", id="transcript")
                    yield TextArea("warming up input…", id="input-pane")
                with Vertical(id="tool-pane"):
                    with VerticalScroll(id="tool-scroll"):
                        yield Static("warming up tool pane…", id="tools")
                    yield Static("phase=warming_up", id="status")
            yield Footer()

        def on_mount(self) -> None:
            self.started_at = time.monotonic()
            self.heartbeat.record_heartbeat(self.started_at)
            self.refresh_views()

            self.watchdog_thread = WatchdogThread(
                heartbeat=self.heartbeat,
                watchdog=self.watchdog,
                poll_interval_ms=self.config.watchdog_poll_interval_ms,
                hard_fail_after_ms=self.config.hard_fail_after_ms,
                on_snapshot=self._on_watchdog_snapshot,
                on_hard_failure=self._on_watchdog_hard_failure,
            )
            self.watchdog_thread.start()

            self.set_interval(self.config.heartbeat_interval_ms / 1000, self._heartbeat_tick)
            self.set_timer(self.config.warmup_delay_ms / 1000, self._start_stressors)

        def _start_stressors(self) -> None:
            if self.stress_started or self.completed:
                return
            self._prime_stress_state(now=time.monotonic())
            self.query_one(TextArea).text = self.state.input_state.buffer or "auto-input idle"
            self.refresh_views()
            self.call_after_refresh(self._continue_startup_after_refresh)

        def _prime_stress_state(self, *, now: float) -> None:
            self.stress_started = True
            self.stress_started_at = now
            self.seeded_history_entries = 0
            self._seed_next_history_chunk()
            self.state.input_state.buffer = "auto-input primed"

        def _continue_startup_after_refresh(self) -> None:
            if self.completed:
                return
            if not self.active_stressors_started:
                self._start_active_stressors()
            if self._seed_next_history_chunk():
                self.refresh_transcript()
                self.refresh_status()
                if self.seeded_history_entries < self.config.profile.history_size:
                    self.call_after_refresh(self._continue_startup_after_refresh)

        def _seed_next_history_chunk(self) -> bool:
            if self.stress_started_at is None:
                return False
            remaining = self.config.profile.history_size - self.seeded_history_entries
            if remaining <= 0:
                return False
            chunk_size = min(self.SEED_CHUNK_SIZE, remaining)
            self.coordinator.seed_state_chunk(
                self.state,
                base_time=self.stress_started_at,
                start_index=self.seeded_history_entries,
                count=chunk_size,
            )
            self.seeded_history_entries += chunk_size
            return True

        def _start_active_stressors(self) -> None:
            if self.completed or self.active_stressors_started:
                return
            self.active_stressors_started = True
            self.set_interval(1 / self.config.profile.assistant_delta_rate, self._assistant_tick)
            self.set_interval(1 / self.config.profile.tool_update_rate, self._tool_tick)
            self.set_interval(self.config.profile.input_submit_interval_ms / 1000, self._input_tick)
            self.set_interval(self.config.profile.layout_toggle_interval_ms / 1000, self._layout_tick)
            self.set_timer(self.config.duration_seconds, self._finish_pass)

        def action_quit(self) -> None:
            self.failure_reason = self.failure_reason or "failed_manual_quit"
            self._stop_watchdog_thread()
            self.exit()

        def on_unmount(self) -> None:
            self._stop_watchdog_thread()

        def _heartbeat_tick(self) -> None:
            now = time.monotonic()
            self.heartbeat.record_heartbeat(now)
            self.refresh_status()

        def _assistant_tick(self) -> None:
            if self.completed:
                return
            now = time.monotonic()
            self.coordinator.assistant_tick(self.state, now=now)
            self.heartbeat.record_transcript_update(now)
            self.refresh_transcript()
            self.refresh_status()

        def _tool_tick(self) -> None:
            if self.completed:
                return
            now = time.monotonic()
            self.coordinator.tool_tick(self.state, now=now)
            self.heartbeat.record_tool_update(now)
            self.refresh_tools()
            self.refresh_status()

        def _input_tick(self) -> None:
            if self.completed:
                return
            now = time.monotonic()
            before_submit = self.state.input_state.submitting
            self.coordinator.input_tick(self.state, now=now)
            if before_submit:
                self.heartbeat.record_input_ack(now)
            else:
                self.heartbeat.record_input_submit(now)
            input_widget = self.query_one(TextArea)
            input_widget.text = self.state.input_state.buffer or "auto-input idle"
            self.refresh_status()

        def _layout_tick(self) -> None:
            if self.completed:
                return
            self.layout_show_tools = not self.layout_show_tools
            self.query_one("#tool-pane").display = self.layout_show_tools
            self.refresh_status()

        def _on_watchdog_snapshot(self, snapshot: WatchdogSnapshot) -> None:
            self.latest_watchdog_snapshot = snapshot

        def _on_watchdog_hard_failure(self, snapshot: WatchdogSnapshot) -> None:
            self.failure_reason = "failed_stall"
            self.latest_watchdog_snapshot = snapshot
            try:
                self.call_from_thread(self._exit_with_failure)
            except RuntimeError:
                from spikes.textual_stability.watchdog import WatchdogThread as _Thread

                _Thread._default_hard_failure(snapshot)

        def _exit_with_failure(self) -> None:
            if self.completed:
                return
            self.completed = True
            self._stop_watchdog_thread()
            self.exit(message=self._result_summary("failed"), return_code=2)

        def _finish_pass(self) -> None:
            if self.completed:
                return
            self.completed = True
            self._stop_watchdog_thread()
            self.exit(message=self._result_summary("pass"), return_code=0)

        def _stop_watchdog_thread(self) -> None:
            if self.watchdog_thread is not None:
                watchdog_thread = self.watchdog_thread
                self.watchdog_thread = None
                watchdog_thread.stop()
                if watchdog_thread is not threading.current_thread():
                    watchdog_thread.join(timeout=1)

        def refresh_views(self) -> None:
            self.refresh_transcript()
            self.refresh_tools()
            self.refresh_status()

        def refresh_transcript(self) -> None:
            transcript = self.query_one("#transcript", Static)
            transcript.update(self._transcript_text())

        def refresh_tools(self) -> None:
            tools = self.query_one("#tools", Static)
            tools.update(self._tools_text())

        def refresh_status(self) -> None:
            status = self.query_one("#status", Static)
            status.update(self._status_text())

        def _transcript_text(self) -> str:
            if not self.stress_started and not self.state.transcript:
                return "warming up transcript…"
            if not self.state.transcript:
                return "No transcript activity yet."
            lines = []
            for entry in self.state.transcript[-200:]:
                suffix = " ..." if entry.streaming else ""
                lines.append(f"[{entry.role}] {entry.text}{suffix}")
            return "\n".join(lines)

        def _tools_text(self) -> str:
            if not self.stress_started and not self.state.tools:
                return "warming up tool pane…"
            if not self.state.tools:
                return "No tool activity yet."
            lines = []
            for tool_id in sorted(self.state.tools):
                entry = self.state.tools[tool_id]
                lines.append(f"{entry.title}  phase={entry.phase}  progress={entry.progress}%  updates={entry.updates}")
            return "\n".join(lines)

        def _status_text(self, *, now: float | None = None) -> str:
            current_time = time.monotonic() if now is None else now
            snapshot = self.latest_watchdog_snapshot or self.watchdog.snapshot(self.heartbeat, now=current_time)
            if self.stress_started and self.stress_started_at is not None:
                remaining = max(0, self.config.duration_seconds - int(current_time - self.stress_started_at))
                phase = "running"
            else:
                remaining = max(0, int((self.config.warmup_delay_ms / 1000) - (current_time - self.started_at)))
                phase = "warming_up"
            return " | ".join(
                [
                    f"phase={phase}",
                    f"profile={self.config.profile.name}",
                    f"remaining={remaining}s",
                    f"events={self.state.health.event_count}",
                    f"heartbeat={snapshot.heartbeat_seq}",
                    f"watchdog={snapshot.watchdog_status}",
                    f"transcript_at={self.state.health.last_transcript_at}",
                    f"tool_at={self.state.health.last_tool_update_at}",
                    f"input_submit={self.state.input_state.last_submit_at}",
                    f"input_ack={self.state.input_state.last_ack_at}",
                ]
            )

        def _result_summary(self, result: str) -> str:
            snapshot = self.latest_watchdog_snapshot or self.watchdog.snapshot(self.heartbeat, now=time.monotonic())
            reason = self.failure_reason or result
            return (
                f"result={result} "
                f"reason={reason} "
                f"events={self.state.health.event_count} "
                f"heartbeat={snapshot.heartbeat_seq} "
                f"watchdog={snapshot.watchdog_status} "
                f"heartbeat_age_ms={snapshot.heartbeat_age_ms:.0f}"
            )

    return TextualStabilityApp


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        app_class = build_app(config)
    except RuntimeError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    app = app_class()
    app.run()
    return app.return_code


if __name__ == "__main__":
    raise SystemExit(main())
