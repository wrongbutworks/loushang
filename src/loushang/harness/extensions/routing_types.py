from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

ExtensionHandler = Callable[[object, object], object | Awaitable[object] | None]
RouteErrorPolicy = Literal["skip", "fail_chain"]


@dataclass(frozen=True)
class RegisteredExtensionHandler:
    local_route_id: str
    event_name: str
    handler: ExtensionHandler
    priority: int = 0
    after: tuple[str, ...] = ()
    before: tuple[str, ...] = ()
    on_error: RouteErrorPolicy = "skip"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        local_route_id = self.local_route_id.strip()
        event_name = self.event_name.strip()
        if not local_route_id:
            raise ValueError("extension route id must not be empty")
        if not event_name:
            raise ValueError("extension route event name must not be empty")
        if not callable(self.handler):
            raise TypeError("extension route handler must be callable")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("extension route priority must be an integer")
        if self.on_error not in {"skip", "fail_chain"}:
            raise ValueError(
                f"unsupported extension route error policy: {self.on_error}"
            )
        object.__setattr__(self, "local_route_id", local_route_id)
        object.__setattr__(self, "event_name", event_name)
        object.__setattr__(self, "after", _normalized_references(self.after))
        object.__setattr__(self, "before", _normalized_references(self.before))
        object.__setattr__(self, "metadata", dict(self.metadata))


def _normalized_references(references: Sequence[str]) -> tuple[str, ...]:
    if isinstance(references, str):
        raise TypeError("extension route references must be a sequence of strings")
    values = tuple(references)
    if not all(isinstance(reference, str) for reference in values):
        raise TypeError("extension route references must be a sequence of strings")
    normalized = tuple(reference.strip() for reference in values)
    if any(not reference for reference in normalized):
        raise ValueError("extension route references must not be empty")
    return normalized


__all__ = [
    "ExtensionHandler",
    "RegisteredExtensionHandler",
    "RouteErrorPolicy",
]
