from __future__ import annotations

import gc
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any, Self

from .base import BufferedTerminalDriver
from .protocol import TerminalProcessDiagnostics


class WindowsConPtyDriver(BufferedTerminalDriver):
    """Low-level pywinpty driver with one explicitly owned reader thread."""

    backend_name = "conpty"

    def __init__(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        columns: int,
        rows: int,
        pty_object: Any,
    ) -> None:
        super().__init__(
            args, cwd=cwd, env=env, columns=columns, rows=rows
        )
        self._pty: Any | None = pty_object
        self._pid = pty_object.pid
        self._exit_status: int | None = None
        self._stop_reader = threading.Event()
        self._reader = threading.Thread(
            target=self._read_loop,
            name=f"loushang-conpty-reader-{self._pid}",
            daemon=True,
        )
        self._reader.start()

    @classmethod
    def spawn(
        cls,
        args: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        columns: int,
        rows: int,
    ) -> Self:
        if os.name != "nt":
            raise RuntimeError("ConPTY is only available on Windows")
        if not args:
            raise ValueError("terminal argv must not be empty")
        try:
            from winpty import PTY
            from winpty.enums import Backend
        except ImportError as error:
            raise RuntimeError(
                "required pywinpty==2.0.15 dependency is unavailable"
            ) from error
        if Backend.ConPTY != 0:
            raise RuntimeError(f"unexpected pywinpty ConPTY backend id: {Backend.ConPTY}")
        executable = _resolve_executable(str(args[0]), env)
        pty_object = PTY(columns, rows, backend=Backend.ConPTY)
        environment = "\0".join(f"{key}={value}" for key, value in env.items()) + "\0"
        arguments = [str(arg) for arg in args[1:]]
        command_line = None if not arguments else " " + subprocess.list2cmdline(arguments)
        spawned = pty_object.spawn(
            str(executable),
            cmdline=command_line,
            cwd=str(cwd),
            env=environment,
        )
        if spawned is False or pty_object.pid is None:
            raise RuntimeError("pywinpty failed to spawn a forced ConPTY process")
        return cls(
            args,
            cwd=cwd,
            env=env,
            columns=columns,
            rows=rows,
            pty_object=pty_object,
        )

    def write(self, text: str) -> None:
        with self._writer_lock:
            if self._closed or self._pty is None:
                raise RuntimeError("terminal driver is closed")
            self._pty.write(text)

    def resize(self, *, columns: int, rows: int) -> None:
        if self._pty is None:
            raise RuntimeError("terminal driver is closed")
        self._pty.set_size(columns, rows)
        self._columns = columns
        self._rows = rows
        self._responder.columns = columns
        self._responder.rows = rows

    def is_alive(self) -> bool:
        return bool(self._pty is not None and self._pty.isalive())

    def wait(self, *, timeout: float) -> int:
        deadline = time.monotonic() + max(0.0, timeout)
        while self.is_alive() and time.monotonic() < deadline:
            self._raise_reader_or_query_error()
            time.sleep(0.01)
        if self.is_alive():
            raise TimeoutError(f"ConPTY process wait timed out:\n{self.diagnostics}")
        if self._pty is not None:
            self._exit_status = self._pty.get_exitstatus()
        self._wait_for_idle_output(timeout=max(0.01, deadline - time.monotonic()))
        return 0 if self._exit_status is None else self._exit_status

    def terminate_tree(self, *, timeout: float) -> None:
        if not self.is_alive() or self._pid is None:
            return
        deadline = time.monotonic() + max(0.0, timeout)
        taskkill = _trusted_taskkill_path(self._env)
        try:
            completed = subprocess.run(
                [str(taskkill), "/PID", str(self._pid), "/T", "/F"],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=max(0.01, deadline - time.monotonic()),
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"taskkill timed out:\n{self.diagnostics}") from error
        self._termination = (
            f"taskkill rc={completed.returncode}; "
            f"stdout={completed.stdout[-500:]!r}; stderr={completed.stderr[-500:]!r}"
        )
        while self.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        if self.is_alive():
            raise TimeoutError(f"ConPTY process tree remained alive:\n{self.diagnostics}")

    def close(self, *, timeout: float = 5.0) -> None:
        with self._close_lock:
            if self._closed:
                return
            deadline = time.monotonic() + max(0.0, timeout)
            try:
                if self.is_alive():
                    self.terminate_tree(timeout=max(0.01, deadline - time.monotonic()))
                self._wait_for_idle_output(
                    timeout=max(0.01, min(0.5, deadline - time.monotonic()))
                )
            finally:
                pty_object, self._pty = self._pty, None
                if pty_object is not None:
                    with suppress(BaseException):
                        self._exit_status = pty_object.get_exitstatus()
                    with suppress(BaseException):
                        pty_object.cancel_io()
                self._stop_reader.set()
                self._reader.join(timeout=max(0.0, deadline - time.monotonic()))
                del pty_object
                gc.collect()
                self._closed = True
            if self._reader.is_alive():
                raise TimeoutError(f"ConPTY reader did not stop:\n{self.diagnostics}")

    @property
    def diagnostics(self) -> TerminalProcessDiagnostics:
        return self._base_diagnostics(
            pid=self._pid,
            exit_status=self._exit_status,
            reader_alive=self._reader.is_alive(),
        )

    def _read_loop(self) -> None:
        try:
            while not self._stop_reader.is_set():
                pty_object = self._pty
                if pty_object is None:
                    break
                try:
                    data = pty_object.read(32768, blocking=False)
                except BaseException:
                    if pty_object.iseof() or not pty_object.isalive():
                        break
                    raise
                if data:
                    self._record_output(data)
                if not data and pty_object.iseof():
                    break
                if not data:
                    time.sleep(0.002)
        except BaseException as error:
            if not self._stop_reader.is_set():
                self._record_reader_error(error)
        finally:
            self._record_reader_done()


def _resolve_executable(command: str, env: Mapping[str, str]) -> Path:
    candidate = Path(command)
    if candidate.is_absolute() and candidate.is_file():
        return candidate
    path = next(
        (value for key, value in env.items() if key.casefold() == "path"),
        None,
    )
    resolved = shutil.which(command, path=path)
    if resolved is None:
        raise FileNotFoundError(f"terminal executable was not found: {command}")
    return Path(resolved).resolve()


def _trusted_taskkill_path(env: Mapping[str, str]) -> Path:
    system_root = next(
        (value for key, value in env.items() if key.casefold() == "systemroot"),
        os.environ.get("SystemRoot", r"C:\Windows"),
    )
    taskkill = Path(system_root) / "System32" / "taskkill.exe"
    if not taskkill.is_file():
        raise FileNotFoundError(f"trusted taskkill.exe was not found: {taskkill}")
    return taskkill
