from __future__ import annotations

import asyncio
import os
import select
import termios
import time
import tty
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from typing import Any, Literal, Protocol, TextIO

from loushang.tui.keyboard_protocol import KeyboardProtocolController


class RuntimeLike(Protocol):
    def request_next_animation_frame(self) -> Any: ...
    def render_now(self) -> Any: ...


@dataclass(slots=True)
class TerminalInputMode:
    stdin: Any
    stdout: TextIO
    bracketed_paste: bool = True
    focus_events: bool = True
    keyboard_protocols: bool = True
    keyboard_fallback_immediate: bool = True
    drain_on_exit: bool = True
    drain_limit: int = 4096
    drain_idle_timeout: float = 0.05
    drain_max_duration: float = 1.0
    _fd: int | None = None
    _original_attrs: list[Any] | None = None
    _enabled: bool = False
    _keyboard_controller: KeyboardProtocolController | None = None

    def __enter__(self) -> TerminalInputMode:
        if not stream_is_tty(self.stdin):
            return self
        self._fd = self.stdin.fileno()
        self._original_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        attrs = [*self._original_attrs[:6], list(self._original_attrs[6])]
        attrs[0] &= ~getattr(termios, "ICRNL", 0)
        attrs[3] &= ~(termios.ECHO | termios.ICANON | getattr(termios, "ISIG", 0))
        attrs[6][termios.VMIN] = 1
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self._fd, termios.TCSADRAIN, attrs)
        if self.bracketed_paste:
            self.stdout.write("\x1b[?2004h")
        if self.focus_events:
            self.stdout.write("\x1b[?1004h")
        if self.keyboard_protocols:
            self._keyboard_controller = KeyboardProtocolController()
            self.stdout.write("".join(self._keyboard_controller.startup_sequences(now_ms=0)))
            if self.keyboard_fallback_immediate:
                self.stdout.write("".join(self._keyboard_controller.fallback_sequences_if_due(now_ms=150)))
        if self.bracketed_paste or self.focus_events or self.keyboard_protocols:
            self.stdout.flush()
        self._enabled = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> Literal[False]:
        del exc_type, exc, traceback
        if not self._enabled or self._fd is None or self._original_attrs is None:
            return False
        try:
            if self.drain_on_exit:
                drain_input(
                    self.stdin,
                    max_bytes=self.drain_limit,
                    idle_timeout=self.drain_idle_timeout,
                    max_duration=self.drain_max_duration,
                )
            if self.bracketed_paste:
                self.stdout.write("\x1b[?2004l")
            if self.focus_events:
                self.stdout.write("\x1b[?1004l")
            if self.keyboard_protocols and self._keyboard_controller is not None:
                self.stdout.write("".join(self._keyboard_controller.shutdown_sequences()))
            if self.bracketed_paste or self.focus_events or self.keyboard_protocols:
                self.stdout.flush()
        finally:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_attrs)
        return False


def drain_input(
    stdin: Any,
    *,
    max_bytes: int = 4096,
    idle_timeout: float = 0.05,
    max_duration: float | None = 1.0,
    now: Callable[[], float] = time.monotonic,
) -> str:
    if max_bytes <= 0:
        return ""
    if isinstance(stdin, StringIO):
        return stdin.read(max_bytes)
    if not stream_is_tty(stdin):
        return ""
    fd = stdin.fileno()
    drained = bytearray()
    deadline = None if max_duration is None else now() + max(0.0, max_duration)
    while len(drained) < max_bytes:
        timeout = idle_timeout
        if deadline is not None:
            remaining = deadline - now()
            if remaining <= 0:
                break
            timeout = min(timeout, remaining)
        try:
            readable, _, _ = select.select([fd], [], [], timeout)
        except (OSError, ValueError):
            break
        if not readable:
            break
        chunk = os.read(fd, min(1024, max_bytes - len(drained)))
        if not chunk:
            break
        drained.extend(chunk)
    return bytes(drained).decode("utf-8", errors="replace")


async def read_input_chunk_or_render_tick(
    stdin: TextIO,
    *,
    runtime: RuntimeLike,
    active_task: asyncio.Task[Any] | None,
    render_wakeup: asyncio.Event | None = None,
    pending_input_idle_ms: int | None = None,
    idle_wakeup_ms: int | None = None,
) -> str | None:
    input_task = asyncio.create_task(read_input_chunk(stdin))
    try:
        while True:
            await asyncio.sleep(0)
            if input_task.done():
                return input_task.result()
            if active_task is not None and active_task.done():
                return None

            wait_for: set[asyncio.Task[Any]] = {input_task}
            if active_task is not None and not active_task.done():
                wait_for.add(active_task)
            render_task: asyncio.Task[bool] | None = None
            if render_wakeup is not None:
                render_task = asyncio.create_task(render_wakeup.wait())
                wait_for.add(render_task)

            decision = runtime.request_next_animation_frame()
            timeout = None
            timeout_reason = "render"
            if decision.render_now:
                runtime.render_now()
                continue
            if decision.delay_ms > 0:
                timeout = decision.delay_ms / 1000
            if pending_input_idle_ms is not None:
                pending_timeout = max(0, pending_input_idle_ms) / 1000
                if timeout is None or pending_timeout <= timeout:
                    timeout = pending_timeout
                    timeout_reason = "pending_input"
            if idle_wakeup_ms is not None:
                idle_timeout = max(0, idle_wakeup_ms) / 1000
                if timeout is None or idle_timeout <= timeout:
                    timeout = idle_timeout
                    timeout_reason = "idle_wakeup"

            done, _pending = await asyncio.wait(wait_for, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            render_wakeup_fired = render_task is not None and render_task in done
            if render_wakeup_fired and render_wakeup is not None:
                render_wakeup.clear()
            if render_task is not None and not render_task.done():
                render_task.cancel()
                try:
                    await render_task
                except asyncio.CancelledError:
                    pass
            if input_task in done:
                return input_task.result()
            if active_task is not None and active_task in done:
                return None
            if render_wakeup_fired:
                continue
            if timeout_reason in {"pending_input", "idle_wakeup"}:
                return None
            runtime.render_now()
    finally:
        if not input_task.done():
            input_task.cancel()
            try:
                await input_task
            except asyncio.CancelledError:
                pass


async def read_input_chunk(stdin: TextIO) -> str:
    if isinstance(stdin, StringIO):
        return stdin.read(1)
    if stream_is_tty(stdin):
        return await _read_tty_input_chunk_async(stdin)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _read_input_chunk_blocking, stdin)


async def _read_tty_input_chunk_async(stdin: Any) -> str:
    fd = stdin.fileno()
    while True:
        try:
            readable, _, _ = select.select([fd], [], [], 0)
        except (OSError, ValueError):
            return ""
        if readable:
            return _read_tty_input_chunk(stdin)
        await asyncio.sleep(0.01)


def _read_input_chunk_blocking(stdin: Any) -> str:
    if stream_is_tty(stdin):
        return _read_tty_input_chunk(stdin)
    return stdin.read(1)


def _read_tty_input_chunk(stdin: Any) -> str:
    fd = stdin.fileno()
    first = os.read(fd, 1)
    if first == b"":
        return ""
    return (first + _read_utf8_tail(fd, first)).decode("utf-8", errors="replace")


def _read_utf8_tail(fd: int, first: bytes) -> bytes:
    needed = _utf8_sequence_length(first[0])
    tail = b""
    while len(tail) < needed - 1:
        chunk = os.read(fd, 1)
        if chunk == b"":
            break
        tail += chunk
    return tail


def _utf8_sequence_length(first_byte: int) -> int:
    if first_byte & 0b1000_0000 == 0:
        return 1
    if first_byte & 0b1110_0000 == 0b1100_0000:
        return 2
    if first_byte & 0b1111_0000 == 0b1110_0000:
        return 3
    if first_byte & 0b1111_1000 == 0b1111_0000:
        return 4
    return 1


def stream_is_tty(stream: Any) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(callable(isatty) and isatty())


__all__ = ["TerminalInputMode", "drain_input", "read_input_chunk", "read_input_chunk_or_render_tick", "stream_is_tty"]
