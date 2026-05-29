from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Literal


WatchdogStatus = Literal["ok", "lagging", "stalled"]


@dataclass
class HeartbeatState:
    last_heartbeat_at: float | None = None
    heartbeat_seq: int = 0
    last_transcript_at: float | None = None
    last_tool_update_at: float | None = None
    last_input_submit_at: float | None = None
    last_input_ack_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_heartbeat(self, now: float) -> None:
        with self._lock:
            self.last_heartbeat_at = now
            self.heartbeat_seq += 1

    def record_transcript_update(self, now: float) -> None:
        with self._lock:
            self.last_transcript_at = now

    def record_tool_update(self, now: float) -> None:
        with self._lock:
            self.last_tool_update_at = now

    def record_input_submit(self, now: float) -> None:
        with self._lock:
            self.last_input_submit_at = now

    def record_input_ack(self, now: float) -> None:
        with self._lock:
            self.last_input_ack_at = now

    def read(self) -> tuple[float | None, int, float | None, float | None, float | None, float | None]:
        with self._lock:
            return (
                self.last_heartbeat_at,
                self.heartbeat_seq,
                self.last_transcript_at,
                self.last_tool_update_at,
                self.last_input_submit_at,
                self.last_input_ack_at,
            )


@dataclass(frozen=True)
class WatchdogSnapshot:
    heartbeat_seq: int
    last_heartbeat_at: float | None
    last_transcript_at: float | None
    last_tool_update_at: float | None
    last_input_submit_at: float | None
    last_input_ack_at: float | None
    heartbeat_age_ms: float
    watchdog_status: WatchdogStatus


@dataclass(frozen=True)
class Watchdog:
    lagging_threshold_ms: int = 1000
    stall_threshold_ms: int = 2000

    def status_at(self, heartbeat: HeartbeatState, *, now: float) -> WatchdogStatus:
        last_heartbeat_at, *_ = heartbeat.read()
        age_ms = self._heartbeat_age_ms(last_heartbeat_at, now=now)
        if age_ms >= self.stall_threshold_ms:
            return "stalled"
        if age_ms >= self.lagging_threshold_ms:
            return "lagging"
        return "ok"

    def snapshot(self, heartbeat: HeartbeatState, *, now: float) -> WatchdogSnapshot:
        (
            last_heartbeat_at,
            heartbeat_seq,
            last_transcript_at,
            last_tool_update_at,
            last_input_submit_at,
            last_input_ack_at,
        ) = heartbeat.read()
        age_ms = self._heartbeat_age_ms(last_heartbeat_at, now=now)
        if age_ms >= self.stall_threshold_ms:
            status: WatchdogStatus = "stalled"
        elif age_ms >= self.lagging_threshold_ms:
            status = "lagging"
        else:
            status = "ok"
        return WatchdogSnapshot(
            heartbeat_seq=heartbeat_seq,
            last_heartbeat_at=last_heartbeat_at,
            last_transcript_at=last_transcript_at,
            last_tool_update_at=last_tool_update_at,
            last_input_submit_at=last_input_submit_at,
            last_input_ack_at=last_input_ack_at,
            heartbeat_age_ms=age_ms,
            watchdog_status=status,
        )

    @staticmethod
    def _heartbeat_age_ms(last_heartbeat_at: float | None, *, now: float) -> float:
        if last_heartbeat_at is None:
            return float("inf")
        return max(0.0, now - last_heartbeat_at) * 1000


class WatchdogThread(threading.Thread):
    def __init__(
        self,
        *,
        heartbeat: HeartbeatState,
        watchdog: Watchdog,
        poll_interval_ms: int,
        hard_fail_after_ms: int,
        on_snapshot: Callable[[WatchdogSnapshot], None] | None = None,
        on_hard_failure: Callable[[WatchdogSnapshot], None] | None = None,
    ) -> None:
        super().__init__(name="textual-stability-watchdog", daemon=True)
        self._heartbeat = heartbeat
        self._watchdog = watchdog
        self._poll_interval_ms = poll_interval_ms
        self._hard_fail_after_ms = hard_fail_after_ms
        self._on_snapshot = on_snapshot
        self._on_hard_failure = on_hard_failure or self._default_hard_failure
        self._stop_event = threading.Event()
        self.latest_snapshot: WatchdogSnapshot | None = None

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            snapshot = self._watchdog.snapshot(self._heartbeat, now=time.monotonic())
            self.latest_snapshot = snapshot
            if self._on_snapshot is not None:
                self._on_snapshot(snapshot)
            if snapshot.heartbeat_age_ms >= self._hard_fail_after_ms:
                self._on_hard_failure(snapshot)
                return
            self._stop_event.wait(self._poll_interval_ms / 1000)

    @staticmethod
    def _default_hard_failure(snapshot: WatchdogSnapshot) -> None:
        sys.stderr.write(
            "Watchdog hard failure: "
            f"status={snapshot.watchdog_status} "
            f"heartbeat_age_ms={snapshot.heartbeat_age_ms:.0f}\n"
        )
        sys.stderr.flush()
        os._exit(2)
