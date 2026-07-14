from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

R = TypeVar("R")
PrepareRefresh = Callable[[], object | Awaitable[object]]
LoadResource = Callable[[], R | None | Awaitable[R | None]]
DiscoverResource = Callable[[R, str], R | Awaitable[R]]
CommitResource = Callable[[R], object | Awaitable[object]]


@dataclass
class ResourceRefreshCoordinator(Generic[R]):
    """Own the ordered resource prepare, load, discover, and commit pipeline."""

    load_resource: LoadResource[R]
    commit_resource: CommitResource[R]
    discover_resource: DiscoverResource[R] | None = None
    discover_resource_async: DiscoverResource[R] | None = None
    prepare_refresh: PrepareRefresh | None = None

    def refresh(self, *, reason: str = "refresh") -> R | None:
        resource = self._load_resource()
        if resource is None:
            return None
        if self.discover_resource is not None:
            discovered = self.discover_resource(resource, reason)
            if inspect.isawaitable(discovered):
                if inspect.iscoroutine(discovered):
                    discovered.close()
                raise TypeError(
                    "Synchronous resource discovery returned an awaitable; "
                    "use refresh_async()."
                )
            resource = discovered
        committed = self.commit_resource(resource)
        if inspect.isawaitable(committed):
            if inspect.iscoroutine(committed):
                committed.close()
            raise TypeError(
                "Synchronous resource commit returned an awaitable; "
                "use refresh_async()."
            )
        return resource

    async def refresh_async(self, *, reason: str = "refresh") -> R | None:
        resource = await self._load_resource_async()
        if resource is None:
            return None
        discover = self.discover_resource_async or self.discover_resource
        if discover is not None:
            discovered = discover(resource, reason)
            if inspect.isawaitable(discovered):
                discovered = await discovered
            resource = discovered
        committed = self.commit_resource(resource)
        if inspect.isawaitable(committed):
            await committed
        return resource

    def _load_resource(self) -> R | None:
        if self.prepare_refresh is not None:
            prepared = self.prepare_refresh()
            if inspect.isawaitable(prepared):
                if inspect.iscoroutine(prepared):
                    prepared.close()
                raise TypeError(
                    "Synchronous resource preparation returned an awaitable; "
                    "use refresh_async()."
                )
        loaded = self.load_resource()
        if inspect.isawaitable(loaded):
            if inspect.iscoroutine(loaded):
                loaded.close()
            raise TypeError(
                "Synchronous resource loading returned an awaitable; "
                "use refresh_async()."
            )
        return loaded

    async def _load_resource_async(self) -> R | None:
        if self.prepare_refresh is not None:
            prepared = self.prepare_refresh()
            if inspect.isawaitable(prepared):
                await prepared
        loaded = self.load_resource()
        if inspect.isawaitable(loaded):
            loaded = await loaded
        return loaded


@dataclass
class RuntimeResourceDiscovery(Generic[R]):
    """Adapt optional sync/async runtime discovery methods to typed callbacks."""

    get_runtime: Callable[[], object | None]

    def discover(self, resource: R, reason: str) -> R | Awaitable[R]:
        runtime = self.get_runtime()
        callback = (
            getattr(runtime, "discover_resources", None)
            if runtime is not None
            else None
        )
        if not callable(callback):
            return resource
        return cast(R | Awaitable[R], _invoke_discovery(callback, resource, reason))

    async def discover_async(self, resource: R, reason: str) -> R:
        runtime = self.get_runtime()
        if runtime is None:
            return resource
        callback = getattr(runtime, "discover_resources_async", None)
        if not callable(callback):
            callback = getattr(runtime, "discover_resources", None)
        if not callable(callback):
            return resource
        discovered = _invoke_discovery(callback, resource, reason)
        if inspect.isawaitable(discovered):
            discovered = await discovered
        return cast(R, discovered)


def _invoke_discovery(
    callback: Callable[..., object], resource: R, reason: str
) -> object:
    if _accepts_keyword(callback, "reason"):
        return callback(resource, reason=reason)
    return callback(resource)


def _accepts_keyword(callback: Callable[..., object], keyword: str) -> bool:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or name == keyword
        for name, parameter in signature.parameters.items()
    )


__all__ = [
    "CommitResource",
    "DiscoverResource",
    "LoadResource",
    "PrepareRefresh",
    "ResourceRefreshCoordinator",
    "RuntimeResourceDiscovery",
]
