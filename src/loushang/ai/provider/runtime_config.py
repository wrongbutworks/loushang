from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterRuntimeConfig:
    pass


AdapterRuntimeConfigResolver = Callable[
    [Mapping[str, object], AdapterRuntimeConfig | None],
    AdapterRuntimeConfig | None,
]


def resolve_adapter_runtime_config(
    resolver: AdapterRuntimeConfigResolver | None,
    adapter_options: Mapping[str, object],
    *,
    current: AdapterRuntimeConfig | None = None,
) -> AdapterRuntimeConfig | None:
    if resolver is None:
        return current
    return resolver(adapter_options, current)
