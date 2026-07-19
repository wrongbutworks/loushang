from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Protocol


class ScreenApprovalSurface(Protocol):
    def open_approval(
        self,
        *,
        action: str,
        risk: str = "",
        action_id: str | None = None,
    ) -> None: ...

    def dismiss_approval(self, action_id: str) -> None: ...

    def clear_approval_surfaces(self) -> None: ...


async def handle_screen_approval(
    session: Any,
    event: dict[str, object],
) -> bool:
    sink = getattr(session, "handle_screen_approval", None)
    if not callable(sink):
        return False
    return bool(await _maybe_await(sink(event)))


def bind_screen_approval_presenter(
    session: Any,
    surface: ScreenApprovalSurface,
    *,
    session_provider: Callable[[], Any] | None = None,
) -> Callable[[], None]:
    setter = getattr(session, "set_approval_presenter", None)
    if not callable(setter):
        return lambda: None

    def present(payload: dict[str, object]) -> None:
        action = payload.get("action")
        risk = payload.get("risk")
        action_id = payload.get("action_id")
        surface.open_approval(
            action=action if isinstance(action, str) else "Approve tool call",
            risk=risk if isinstance(risk, str) else "",
            action_id=action_id if isinstance(action_id, str) else None,
        )

    setter(present, dismisser=surface.dismiss_approval)

    def unbind() -> None:
        target = session_provider() if session_provider is not None else session
        _unbind_session_approval_presenter(target)
        if target is not session:
            _unbind_session_approval_presenter(session)

    return unbind


def runtime_session(runtime: Any, fallback: Any) -> Any:
    getter = getattr(runtime, "get_current_session", None)
    if callable(getter):
        current = getter()
        if current is not None:
            return current
    current = getattr(runtime, "current_session", None)
    return current if current is not None else fallback


def bind_screen_session_transition(
    runtime: Any,
    surface: ScreenApprovalSurface,
) -> Callable[[], None]:
    subscribe = getattr(runtime, "subscribe_after_session_invalidate", None)
    if not callable(subscribe):
        subscribe = getattr(runtime, "subscribe_before_session_invalidate", None)
    if not callable(subscribe):
        return lambda: None
    unsubscribe = subscribe(surface.clear_approval_surfaces)
    return unsubscribe if callable(unsubscribe) else lambda: None


def _unbind_session_approval_presenter(session: Any) -> None:
    host_unbind = getattr(session, "_unbind_approval_presenter_host", None)
    if callable(host_unbind):
        host_unbind()
        return
    setter = getattr(session, "set_approval_presenter", None)
    if callable(setter):
        setter(None)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "ScreenApprovalSurface",
    "bind_screen_approval_presenter",
    "bind_screen_session_transition",
    "handle_screen_approval",
    "runtime_session",
]
