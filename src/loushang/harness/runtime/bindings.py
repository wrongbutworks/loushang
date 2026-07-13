from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

B = TypeVar("B")


class RuntimeBindingState(Generic[B]):
    """Own live runtime bindings and invalidate generation-scoped contexts."""

    def __init__(
        self,
        bindings: B | None = None,
        *,
        unbound_message: str = "Runtime bindings have not been set.",
        stale_message: str = "Runtime context is stale.",
    ) -> None:
        self._bindings = bindings
        self._generation = 0
        self._unbound_message = unbound_message
        self._stale_message = stale_message

    @property
    def bindings(self) -> B | None:
        return self._bindings

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def stale_message(self) -> str:
        return self._stale_message

    @property
    def is_bound(self) -> bool:
        return self._bindings is not None

    def bind(self, bindings: B) -> None:
        self._bindings = bindings

    def refresh(self, bindings: B) -> None:
        self._bindings = bindings

    def invalidate(self, message: str | None = None) -> None:
        self._generation += 1
        if message is not None:
            self._stale_message = message

    def capture(self) -> RuntimeBindingLease[B]:
        return RuntimeBindingLease(state=self, generation=self._generation)

    def require(self, *, generation: int | None = None) -> B:
        if generation is not None and generation != self._generation:
            raise RuntimeError(self._stale_message)
        bindings = self._bindings
        if bindings is None:
            raise RuntimeError(self._unbound_message)
        return bindings


@dataclass(frozen=True)
class RuntimeBindingLease(Generic[B]):
    state: RuntimeBindingState[B]
    generation: int

    @property
    def is_current(self) -> bool:
        return self.generation == self.state.generation

    def require(self) -> B:
        return self.state.require(generation=self.generation)


__all__ = ["RuntimeBindingLease", "RuntimeBindingState"]
