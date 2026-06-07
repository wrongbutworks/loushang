from __future__ import annotations

import asyncio
import inspect
import os
import signal as signal_module
import tempfile
from collections.abc import Awaitable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol, TextIO

from loushang.coding.exec.types import (
    ExecOutputChunk,
    ExecRequest,
    ExecResult,
    ExecUpdateCallback,
)


class ExecBackend(Protocol):
    def __call__(
        self,
        request: ExecRequest,
        *,
        signal: object | None = None,
        on_update: ExecUpdateCallback | None = None,
    ) -> Awaitable[ExecResult] | ExecResult: ...


class ExecService:
    def __init__(self, *, backend: ExecBackend | None = None) -> None:
        self._backend = backend

    async def execute(
        self,
        request: ExecRequest,
        *,
        signal: object | None = None,
        on_update: ExecUpdateCallback | None = None,
    ) -> ExecResult:
        if self._backend is not None:
            result = self._backend(request, signal=signal, on_update=on_update)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, ExecResult):
                raise TypeError("exec backend must return ExecResult")
            return result

        env = os.environ.copy()
        env.update(dict(request.env))

        process = await asyncio.create_subprocess_exec(
            *request.command,
            cwd=request.cwd,
            env=env,
            start_new_session=True,
            stdin=asyncio.subprocess.PIPE if request.stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_capture = _StreamCapture(
            stream_name="stdout",
            capture_full_output=request.capture_full_output,
            rolling_max_bytes=request.rolling_max_bytes,
            artifact_dir=request.artifact_dir,
        )
        stderr_capture = _StreamCapture(
            stream_name="stderr",
            capture_full_output=request.capture_full_output,
            rolling_max_bytes=request.rolling_max_bytes,
            artifact_dir=request.artifact_dir,
        )
        output_capture = _OutputCapture(
            capture_full_output=request.capture_full_output,
            rolling_max_bytes=request.rolling_max_bytes,
        )

        async def _read_stream(stream_name: str, stream, sink: _StreamCapture) -> None:
            while True:
                chunk = await stream.readline()
                if not chunk:
                    break
                text = chunk.decode()
                sink.append(text)
                output_chunk = ExecOutputChunk(stream=stream_name, text=text)
                output_capture.append(output_chunk)
                if on_update is not None:
                    update = on_update(output_chunk)
                    if inspect.isawaitable(update):
                        await update

        stdout_task = asyncio.create_task(_read_stream("stdout", process.stdout, stdout_capture))
        stderr_task = asyncio.create_task(_read_stream("stderr", process.stderr, stderr_capture))
        wait_task = asyncio.create_task(process.wait())

        if process.stdin is not None:
            input_bytes = request.stdin.encode() if request.stdin is not None else b""
            process.stdin.write(input_bytes)
            await process.stdin.drain()
            process.stdin.close()

        abort_task = asyncio.create_task(_wait_for_abort(signal)) if signal is not None else None
        timed_out = False
        cancelled = False

        try:
            if request.timeout_seconds is None and abort_task is None:
                await wait_task
            else:
                waiters = {wait_task}
                if abort_task is not None:
                    waiters.add(abort_task)
                done, pending = await asyncio.wait(
                    waiters,
                    timeout=request.timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if wait_task in done:
                    pass
                elif abort_task is not None and abort_task in done:
                    cancelled = True
                    _kill_process(process)
                    await wait_task
                else:
                    timed_out = True
                    _kill_process(process)
                    await wait_task
                for task in pending:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        finally:
            if abort_task is not None and not abort_task.done():
                abort_task.cancel()
                await asyncio.gather(abort_task, return_exceptions=True)
            await asyncio.gather(stdout_task, stderr_task)
            stdout_capture.close()
            stderr_capture.close()

        stdout = stdout_capture.content
        stderr = stderr_capture.content
        stdout_preview, stdout_artifact_path = _build_preview_from_capture(
            stdout_capture,
            max_lines=request.preview_max_lines,
            max_bytes=request.preview_max_bytes,
        )
        stderr_preview, stderr_artifact_path = _build_preview_from_capture(
            stderr_capture,
            max_lines=request.preview_max_lines,
            max_bytes=request.preview_max_bytes,
        )
        return ExecResult(
            exit_code=process.returncode if process.returncode is not None else (-1 if timed_out or cancelled else 0),
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
            stdout_chunks=tuple(stdout_capture.chunks),
            stderr_chunks=tuple(stderr_capture.chunks),
            output_chunks=tuple(output_capture.chunks),
            stdout_preview=stdout_preview.content,
            stderr_preview=stderr_preview.content,
            stdout_truncated=stdout_preview.truncated,
            stdout_truncated_by=stdout_preview.truncated_by,
            stderr_truncated=stderr_preview.truncated,
            stderr_truncated_by=stderr_preview.truncated_by,
            stdout_artifact_path=stdout_artifact_path,
            stderr_artifact_path=stderr_artifact_path,
            stdout_total_lines=stdout_capture.total_lines,
            stdout_total_bytes=stdout_capture.total_bytes,
            stderr_total_lines=stderr_capture.total_lines,
            stderr_total_bytes=stderr_capture.total_bytes,
        )


@dataclass
class _StreamCapture:
    stream_name: str
    capture_full_output: bool
    rolling_max_bytes: int
    artifact_dir: str | None
    chunks: list[str] = field(default_factory=list)
    _chunk_bytes: int = 0
    _artifact_path: str | None = None
    _artifact_handle: TextIO | None = None
    _rolled: bool = False
    _total_bytes: int = 0
    _total_lines: int = 0

    @property
    def content(self) -> str:
        return "".join(self.chunks)

    @property
    def artifact_path(self) -> str | None:
        return self._artifact_path

    @property
    def rolled(self) -> bool:
        return self._rolled

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def total_lines(self) -> int:
        return self._total_lines

    def append(self, text: str) -> None:
        if not text:
            return
        self._total_bytes += len(text.encode("utf-8"))
        self._total_lines += len(text.splitlines())
        if self.capture_full_output:
            self.chunks.append(text)
            return

        self._ensure_artifact_handle().write(text)
        self.chunks.append(text)
        self._chunk_bytes += len(text.encode("utf-8"))
        self._trim_rolling_chunks()

    def close(self) -> None:
        if self._artifact_handle is not None:
            self._artifact_handle.close()
            self._artifact_handle = None

    def discard_artifact(self) -> None:
        if self._artifact_path is None:
            return
        try:
            Path(self._artifact_path).unlink(missing_ok=True)
        finally:
            self._artifact_path = None

    def _ensure_artifact_handle(self) -> TextIO:
        if self._artifact_handle is not None:
            return self._artifact_handle
        fd, path = tempfile.mkstemp(
            prefix=f"loushang-exec-{self.stream_name}-",
            suffix=".log",
            dir=self.artifact_dir,
        )
        self._artifact_path = path
        self._artifact_handle = os.fdopen(fd, "w", encoding="utf-8")
        return self._artifact_handle

    def _trim_rolling_chunks(self) -> None:
        while self._chunk_bytes > self.rolling_max_bytes and len(self.chunks) > 1:
            removed = self.chunks.pop(0)
            self._chunk_bytes -= len(removed.encode("utf-8"))
            self._rolled = True
        if self._chunk_bytes <= self.rolling_max_bytes or not self.chunks:
            return
        from loushang.coding.tools.truncate import truncate_tail

        trimmed = truncate_tail(
            self.chunks[0],
            max_lines=1_000_000,
            max_bytes=self.rolling_max_bytes,
        ).content
        self.chunks[0] = trimmed
        self._chunk_bytes = len(trimmed.encode("utf-8"))
        self._rolled = True


@dataclass
class _OutputCapture:
    capture_full_output: bool
    rolling_max_bytes: int
    chunks: list[ExecOutputChunk] = field(default_factory=list)
    _chunk_bytes: int = 0

    def append(self, chunk: ExecOutputChunk) -> None:
        if not chunk.text:
            return
        self.chunks.append(chunk)
        if self.capture_full_output:
            return
        self._chunk_bytes += len(chunk.text.encode("utf-8"))
        self._trim_rolling_chunks()

    def _trim_rolling_chunks(self) -> None:
        while self._chunk_bytes > self.rolling_max_bytes and len(self.chunks) > 1:
            removed = self.chunks.pop(0)
            self._chunk_bytes -= len(removed.text.encode("utf-8"))
        if self._chunk_bytes <= self.rolling_max_bytes or not self.chunks:
            return
        from loushang.coding.tools.truncate import truncate_tail

        trimmed = truncate_tail(
            self.chunks[0].text,
            max_lines=1_000_000,
            max_bytes=self.rolling_max_bytes,
        ).content
        self.chunks[0] = ExecOutputChunk(stream=self.chunks[0].stream, text=trimmed)
        self._chunk_bytes = len(trimmed.encode("utf-8"))


def _kill_process(process: asyncio.subprocess.Process) -> None:
    try:
        if process.pid is not None:
            os.killpg(process.pid, signal_module.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except ProcessLookupError:
            return


async def _wait_for_abort(signal: object | None) -> None:
    while signal is not None and not getattr(signal, "aborted", False):
        await asyncio.sleep(0.01)


def _build_preview(
    content: str,
    *,
    max_lines: int,
    max_bytes: int,
    artifact_dir: str | None,
    stream_name: str,
):
    from loushang.coding.tools.truncate import truncate_tail

    preview = truncate_tail(content, max_lines=max_lines, max_bytes=max_bytes)
    if not preview.truncated or not content:
        return preview, None
    artifact_path = _write_output_artifact(content, artifact_dir=artifact_dir, stream_name=stream_name)
    return preview, artifact_path


def _build_preview_from_capture(
    capture: _StreamCapture,
    *,
    max_lines: int,
    max_bytes: int,
):
    if capture.capture_full_output:
        return _build_preview(
            capture.content,
            max_lines=max_lines,
            max_bytes=max_bytes,
            artifact_dir=capture.artifact_dir,
            stream_name=capture.stream_name,
        )

    from loushang.coding.tools.truncate import truncate_tail

    preview = truncate_tail(capture.content, max_lines=max_lines, max_bytes=max_bytes)
    truncated = preview.truncated or capture.rolled
    if not truncated or not capture.content:
        capture.discard_artifact()
        return preview, None
    if preview.truncated:
        return preview, capture.artifact_path
    return replace(preview, truncated=True, truncated_by="bytes"), capture.artifact_path


def _write_output_artifact(content: str, *, artifact_dir: str | None, stream_name: str) -> str:
    fd, path = tempfile.mkstemp(prefix=f"loushang-exec-{stream_name}-", suffix=".log", dir=artifact_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception:
        os.close(fd)
        raise
    return path
