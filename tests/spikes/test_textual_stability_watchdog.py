from __future__ import annotations


def test_watchdog_reports_ok_lagging_and_stalled_from_heartbeat_age() -> None:
    from spikes.textual_stability.watchdog import HeartbeatState, Watchdog

    heartbeat = HeartbeatState(last_heartbeat_at=10.0, heartbeat_seq=5)
    watchdog = Watchdog(lagging_threshold_ms=1000, stall_threshold_ms=2000)

    assert watchdog.status_at(heartbeat, now=10.5) == "ok"
    assert watchdog.status_at(heartbeat, now=11.3) == "lagging"
    assert watchdog.status_at(heartbeat, now=12.5) == "stalled"


def test_watchdog_snapshot_tracks_transcript_tool_and_input_activity() -> None:
    from spikes.textual_stability.watchdog import HeartbeatState, Watchdog

    heartbeat = HeartbeatState()
    heartbeat.record_heartbeat(3.0)
    heartbeat.record_transcript_update(3.1)
    heartbeat.record_tool_update(3.2)
    heartbeat.record_input_submit(3.3)
    heartbeat.record_input_ack(3.4)

    snapshot = Watchdog().snapshot(heartbeat, now=3.5)

    assert snapshot.heartbeat_seq == 1
    assert snapshot.last_heartbeat_at == 3.0
    assert snapshot.last_transcript_at == 3.1
    assert snapshot.last_tool_update_at == 3.2
    assert snapshot.last_input_submit_at == 3.3
    assert snapshot.last_input_ack_at == 3.4
    assert snapshot.watchdog_status == "ok"
