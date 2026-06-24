from __future__ import annotations

from collections.abc import Callable

AdapterRuntimeConfigResolver = Callable[[object | None], object | None]


def resolve_adapter_runtime_config(
    resolver: AdapterRuntimeConfigResolver | None,
    *,
    current: object | None = None,
) -> object | None:
    if resolver is None:
        return current
    return resolver(current)
