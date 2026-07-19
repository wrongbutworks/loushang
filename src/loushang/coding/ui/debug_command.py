from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from loushang.coding.diagnostics.debug_status import debug_status_text
from loushang.coding.interaction.intent import DebugIntent


class Renderer(Protocol):
    def render_status(self, text: str) -> None: ...


class StableEmit(Protocol):
    def __call__(self, write_callable: Callable[[], None], *, label: str) -> Awaitable[None]: ...


class TraceFn(Protocol):
    def __call__(self, name: str, **data: Any) -> None: ...


EnableDebug = Callable[..., Path]
DisableDebug = Callable[[], None]


class DebugCommandHandler:
    def __init__(
        self,
        *,
        session: Any,
        cwd: str,
        renderer: Renderer,
        emit: StableEmit,
        trace: TraceFn,
        enable: EnableDebug,
        disable: DisableDebug,
    ) -> None:
        self._session = session
        self._cwd = cwd
        self._renderer = renderer
        self._emit = emit
        self._trace = trace
        self._enable = enable
        self._disable = disable

    async def handle(self, intent: DebugIntent) -> None:
        if not intent.enabled:
            self._disable()
            self._trace("debug.disabled")
            await self._emit(
                lambda: self._renderer.render_status("Debug logging disabled."),
                label="debug:disabled",
            )
            return None

        debug_path = self._enable(session=self._session, scopes=intent.scopes)
        self._trace("debug.enabled", path=str(debug_path), scopes=list(intent.scopes))
        await self._emit(
            lambda: self._renderer.render_status(debug_status_text(debug_path, scopes=intent.scopes, cwd=self._cwd)),
            label="debug:enabled",
        )
        return None


__all__ = ["DebugCommandHandler"]
