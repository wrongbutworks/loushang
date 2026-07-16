from __future__ import annotations

from collections.abc import Awaitable, Callable

from loushang.coding.event import AgentSessionEvent
from loushang.harness.events import OrderedEventBus

SessionEventListener = Callable[[AgentSessionEvent], Awaitable[None] | None]


class SessionEventBus(OrderedEventBus[AgentSessionEvent]):
    def __init__(self) -> None:
        super().__init__(
            async_listener_error=(
                "Async session listeners require a running event loop."
            )
        )
