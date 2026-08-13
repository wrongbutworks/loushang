from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

from loushang.tui import strip_control_sequences


@pytest.mark.tui_terminal_contract
def test_screen_tui_cli_pty_smoke_quit_cleans_bottom_frame() -> None:
    if os.name == "nt":
        pytest.skip("PTY smoke uses POSIX pty")

    output, returncode = _run_pty_command(
        [sys.executable, "-m", "loushang.coding.cli", "--tui"],
        input_text="/quit\r",
        cwd=_repo_root(),
    )

    assert returncode == 0
    assert "Welcome to Loushang CLI" in strip_control_sequences(output)
    assert "\x1b[?25l" in output
    assert "\x1b[?2026h" in output
    assert "\x1b[2K" in output
    final_sync_end = output.rfind("\x1b[?2026l")
    assert final_sync_end != -1
    final_tail = strip_control_sequences(output[final_sync_end:])
    assert " | idle" not in final_tail
    assert " | running" not in final_tail


@pytest.mark.tui_tmux_integration
def test_screen_tui_tmux_pty_preserves_compact_history_and_streamed_tail(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        pytest.skip("tmux PTY regression uses POSIX terminals")
    tmux = shutil.which("tmux")
    if tmux is None and os.environ.get("LOUSHANG_REQUIRE_TMUX") == "1":
        pytest.fail("required tmux executable was not found")
    if tmux is None:
        pytest.skip("tmux is not installed")

    captured = _run_tmux_fixture(
        tmp_path=tmp_path,
        tmux=tmux,
        fixture_name="compact_pty_fixture.py",
        ready_name="compact-playback.ready",
        socket_name=f"loushang-compact-{os.getpid()}",
        session_name="compact",
        visible_sentinel="AFTER_COMPACT_040",
    )

    early_lines = tuple(f"PLAYBACK_EARLY_{index:03d}" for index in range(1, 81))
    after_lines = tuple(f"AFTER_COMPACT_{index:03d}" for index in range(1, 41))
    _assert_ordered_lines(captured, early_lines)
    _assert_ordered_lines(captured, after_lines)
    assert captured.count(after_lines[-1]) == 1
    assert "Context compacted (500000 tokens before)" in captured
    assert "hidden summary line one" not in captured
    assert "hidden summary line two" not in captured


@pytest.mark.tui_tmux_integration
def test_screen_tui_tmux_pty_auto_compaction_preserves_history_and_resume(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        pytest.skip("tmux PTY regression uses POSIX terminals")
    tmux = shutil.which("tmux")
    if tmux is None and os.environ.get("LOUSHANG_REQUIRE_TMUX") == "1":
        pytest.fail("required tmux executable was not found")
    if tmux is None:
        pytest.skip("tmux is not installed")

    evidence_file = tmp_path / "auto-compact-evidence.json"
    session_dir = tmp_path / "sessions"
    captured = _run_tmux_fixture(
        tmp_path=tmp_path,
        tmux=tmux,
        fixture_name="auto_compact_pty_fixture.py",
        ready_name="auto-compact-playback.ready",
        socket_name=f"loushang-auto-compact-{os.getpid()}",
        session_name="auto-compact",
        extra_args=(
            "--evidence-file",
            str(evidence_file),
            "--session-dir",
            str(session_dir),
        ),
        ready_timeout_seconds=30,
        visible_sentinel="AUTO_AFTER_040",
    )

    early_lines = tuple(f"AUTO_EARLY_{index:03d}" for index in range(1, 81))
    after_lines = tuple(f"AUTO_AFTER_{index:03d}" for index in range(1, 41))
    _assert_ordered_lines(captured, early_lines)
    _assert_ordered_lines(captured, after_lines)
    assert captured.count(after_lines[-1]) == 1
    assert "Context compacted (" in captured
    assert "AUTO_COMPACT_PRIVATE_SUMMARY" not in captured

    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert evidence["entryCount"] == 5
    assert evidence["checkpointCount"] == 1
    assert evidence["compactionEventTypes"] == [
        "compaction_start",
        "compaction_end",
    ]
    assert evidence["compactionReasons"] == ["threshold", "threshold"]
    assert evidence["compactionStages"] == ["started", "committed"]
    assert evidence["fullHistoryHasEarly"] is True
    assert evidence["fullHistoryHasAfter"] is True
    assert evidence["resumeContextHasSummary"] is True
    assert evidence["resumeContextHasAfter"] is True
    assert evidence["resumeHistoryCheckpointCount"] == 1
    assert evidence["resumeHistoryHasEarly"] is True
    assert evidence["resumeHistoryHasAfter"] is True

    session_file = Path(evidence["sessionFile"])
    assert session_file.is_file()
    jsonl = session_file.read_text(encoding="utf-8")
    records = [json.loads(line) for line in jsonl.splitlines()]
    assert (
        sum(record.get("kind") == "context.compaction_checkpoint" for record in records)
        == 1
    )
    assert early_lines[0] in jsonl
    assert early_lines[-1] in jsonl
    assert after_lines[0] in jsonl
    assert after_lines[-1] in jsonl


def _run_tmux_fixture(
    *,
    tmp_path: Path,
    tmux: str,
    fixture_name: str,
    ready_name: str,
    socket_name: str,
    session_name: str,
    extra_args: tuple[str, ...] = (),
    ready_timeout_seconds: float = 15,
    visible_sentinel: str,
) -> str:
    repo_root = _repo_root()
    ready_file = tmp_path / ready_name
    tmux_config = tmp_path / f"{session_name}.tmux.conf"
    tmux_config.write_text("set-option -g history-limit 20000\n", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            str(repo_root / "tests/coding/tui_support" / fixture_name),
            "--ready-file",
            str(ready_file),
            *extra_args,
        ]
    )
    env = _subprocess_env(repo_root)
    tmux_args = [tmux, "-f", str(tmux_config), "-L", socket_name]
    target = f"{session_name}:0.0"
    try:
        started = subprocess.run(
            [
                *tmux_args,
                "new-session",
                "-d",
                "-x",
                "80",
                "-y",
                "18",
                "-s",
                session_name,
                command,
            ],
            cwd=repo_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        assert started.returncode == 0, started.stderr
        deadline = time.monotonic() + ready_timeout_seconds
        while time.monotonic() < deadline and not ready_file.exists():
            time.sleep(0.05)
        assert ready_file.exists(), _capture_tmux(
            tmux_args,
            env=env,
            cwd=repo_root,
            target=target,
        )
        captured = _capture_tmux(
            tmux_args,
            env=env,
            cwd=repo_root,
            target=target,
        )
        while time.monotonic() < deadline:
            if visible_sentinel in captured:
                return captured
            time.sleep(0.05)
            captured = _capture_tmux(
                tmux_args,
                env=env,
                cwd=repo_root,
                target=target,
            )
        raise AssertionError(
            f"tmux pane did not show {visible_sentinel!r} before deadline:\n{captured}"
        )
    finally:
        subprocess.run(
            [*tmux_args, "kill-server"],
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )


def _assert_ordered_lines(captured: str, lines: tuple[str, ...]) -> None:
    counts = {line: captured.count(line) for line in lines}
    assert all(count >= 1 for count in counts.values()), (counts, captured)
    positions = [captured.find(line) for line in lines]
    assert positions == sorted(positions)


def _capture_tmux(
    tmux_args: list[str],
    *,
    env: dict[str, str],
    cwd: Path,
    target: str = "compact:0.0",
) -> str:
    captured = subprocess.run(
        [
            *tmux_args,
            "capture-pane",
            "-p",
            "-J",
            "-S",
            "-",
            "-t",
            target,
        ],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    return captured.stdout + captured.stderr


def _run_pty_command(
    args: list[str],
    *,
    input_text: str,
    cwd: Path,
    timeout_seconds: float = 12.0,
) -> tuple[str, int]:
    import pty
    import select

    master_fd, slave_fd = pty.openpty()
    env = _subprocess_env(cwd)
    process = subprocess.Popen(
        args,
        cwd=cwd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        env=env,
    )
    os.close(slave_fd)
    output = bytearray()
    input_sent = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            if not input_sent and b"\x1b[?25h" in output:
                os.write(master_fd, input_text.encode())
                input_sent = True
            readable, _, _ = select.select([master_fd], [], [], 0.05)
            if readable:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            if process.poll() is not None:
                output.extend(_read_available(master_fd))
                break
        if process.poll() is None:
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
                raise AssertionError(
                    f"PTY command timed out; output:\n{output.decode(errors='replace')}"
                )
            else:
                output.extend(_read_available(master_fd))
        if process.returncode is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
            raise AssertionError(
                f"PTY command timed out; output:\n{output.decode(errors='replace')}"
            )
        return output.decode(errors="replace"), process.returncode
    finally:
        with suppress(OSError):
            os.close(master_fd)


def _read_available(fd: int) -> bytes:
    import select

    output = bytearray()
    while True:
        readable, _, _ = select.select([fd], [], [], 0)
        if not readable:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        output.extend(chunk)
    return bytes(output)


def _subprocess_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(repo_root / "src")
    if env.get("PYTHONPATH"):
        pythonpath = f"{pythonpath}{os.pathsep}{env['PYTHONPATH']}"
    env.update(
        {
            "PYTHONPATH": pythonpath,
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
        }
    )
    return env


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
