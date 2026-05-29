from __future__ import annotations


def test_run_lifecycle_tracks_work_runs_and_abort_settling() -> None:
    from loushang.coding.ui.lifecycle import RunLifecycle

    lifecycle = RunLifecycle()

    assert lifecycle.active is False
    assert lifecycle.active_id == 0
    assert lifecycle.aborted_id is None
    assert lifecycle.abort_is_settling() is False
    assert lifecycle.visible_running(session_running=False) is False
    assert lifecycle.visible_running(session_running=True) is True

    first_run_id = lifecycle.begin_work()

    assert first_run_id == 1
    assert lifecycle.active is True
    assert lifecycle.visible_running(session_running=False) is True

    lifecycle.mark_abort_requested()

    assert lifecycle.aborted_id == 1
    assert lifecycle.abort_is_settling() is True

    lifecycle.end_work()

    assert lifecycle.active is False
    assert lifecycle.abort_is_settling() is False
    assert lifecycle.aborted_id == 1

    lifecycle.clear_aborted(first_run_id)

    assert lifecycle.aborted_id is None


def test_run_lifecycle_ignores_abort_marks_when_idle() -> None:
    from loushang.coding.ui.lifecycle import RunLifecycle

    lifecycle = RunLifecycle()

    lifecycle.mark_abort_requested()

    assert lifecycle.aborted_id is None

