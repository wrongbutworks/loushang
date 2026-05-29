from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

from loushang.tui import strip_control_sequences


def test_native_tui_cli_pty_smoke_quit_cleans_bottom_frame() -> None:
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


def _run_pty_command(
    args: list[str],
    *,
    input_text: str,
    cwd: Path,
    timeout_seconds: float = 12.0,
) -> tuple[str, int]:
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
                raise AssertionError(f"PTY command timed out; output:\n{output.decode(errors='replace')}")
            else:
                output.extend(_read_available(master_fd))
        if process.returncode is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
            raise AssertionError(f"PTY command timed out; output:\n{output.decode(errors='replace')}")
        return output.decode(errors="replace"), process.returncode
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass


def _read_available(fd: int) -> bytes:
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
