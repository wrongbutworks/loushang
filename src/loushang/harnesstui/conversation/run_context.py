from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol


class TraceFn(Protocol):
    """Trace one interaction lifecycle fact."""

    def __call__(self, name: str, **data: Any) -> None: ...


class StableEmit(Protocol):
    """Emit one terminal write through the caller's stable-write boundary."""

    def __call__(
        self,
        write_callable: Callable[[], None],
        *,
        label: str,
    ) -> Awaitable[None]: ...


class ExitContext(Protocol):
    """Minimal context-manager exit hook owned by a product adapter."""

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> object: ...


@dataclass
class InteractionRunContext:
    """Own close ordering for one product-neutral terminal interaction run.

    The injected exit context may represent observability or another
    product-owned resource. This object coordinates only terminal interaction
    cleanup; it does not create Sessions or persist conversation state.
    """

    emit: StableEmit
    _unsubscribe: Callable[[], None]
    _exit_context: ExitContext
    _trace: TraceFn
    _closed: bool = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            try:
                self._trace("tui.end")
            finally:
                self._unsubscribe()
        finally:
            self._exit_context.__exit__(None, None, None)


def subscribe_events(source: object, listener: object) -> Callable[[], None]:
    """Subscribe when supported and always return a safe unsubscribe hook."""

    subscribe = getattr(source, "subscribe", None)
    if callable(subscribe):
        unsubscribe = subscribe(listener)
        if callable(unsubscribe):
            return unsubscribe
    return lambda: None


def stable_emit_factory(*, trace: TraceFn, interactive: bool) -> StableEmit:
    """Create a traced stable terminal-write boundary."""

    async def emit(write_callable: Callable[[], None], *, label: str) -> None:
        started = time.monotonic()
        trace("emit.start", label=label, interactive=interactive)
        try:
            write_callable()
        except Exception as error:
            trace(
                "emit.error",
                label=label,
                elapsed_s=time.monotonic() - started,
                error=str(error) or error.__class__.__name__,
            )
            raise
        trace("emit.end", label=label, elapsed_s=time.monotonic() - started)

    return emit


__all__ = [
    "ExitContext",
    "InteractionRunContext",
    "StableEmit",
    "TraceFn",
    "stable_emit_factory",
    "subscribe_events",
]
