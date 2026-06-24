from __future__ import annotations

import asyncio
import inspect
from typing import Protocol, runtime_checkable


@runtime_checkable
class CancellationSignal(Protocol):
    def is_cancelled(self) -> bool: ...

    async def wait(self) -> None: ...


def is_signal_cancelled(signal: object | None) -> bool:
    if signal is None:
        return False
    is_cancelled = getattr(signal, "is_cancelled", None)
    if callable(is_cancelled):
        try:
            return bool(is_cancelled())
        except Exception:
            return False
    is_set = getattr(signal, "is_set", None)
    if callable(is_set):
        try:
            return bool(is_set())
        except Exception:
            return False
    return bool(
        getattr(signal, "aborted", False) or getattr(signal, "cancelled", False)
    )


async def wait_signal_cancelled(signal: object | None) -> None:
    if signal is None or is_signal_cancelled(signal):
        return
    wait = getattr(signal, "wait", None)
    if callable(wait):
        result = wait()
        if inspect.isawaitable(result):
            await result
        return
    while not is_signal_cancelled(signal):
        await asyncio.sleep(0.05)


def has_cancellation_signal(signal: object | None) -> bool:
    return signal is not None


__all__ = [
    "CancellationSignal",
    "has_cancellation_signal",
    "is_signal_cancelled",
    "wait_signal_cancelled",
]
