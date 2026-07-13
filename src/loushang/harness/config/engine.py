from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Generic, TypeVar

from loushang.harness.config.store import JsonConfigStore
from loushang.harness.config.types import (
    ConfigCodec,
    ConfigIssue,
    ConfigLayer,
    ConfigSnapshot,
    ConfigStore,
)

T = TypeVar("T")
ConfigListener = Callable[[T], None]


class LayeredConfig(Generic[T]):
    def __init__(
        self,
        *,
        codec: ConfigCodec[T],
        layers: Sequence[ConfigLayer],
        initial: Mapping[str, Mapping[str, object] | T] | None = None,
        store: ConfigStore | None = None,
    ) -> None:
        self._codec = codec
        self._layers = tuple(layers)
        self._layers_by_name = {layer.name: layer for layer in self._layers}
        if len(self._layers_by_name) != len(self._layers):
            raise ValueError("config layer names must be unique")
        self._store = store or JsonConfigStore()
        self._patches: dict[str, dict[str, object]] = {
            layer.name: {} for layer in self._layers
        }
        self._issues: list[ConfigIssue] = []
        self._listeners: list[ConfigListener[T]] = []
        self._load_persistent_layers()
        for layer_name, value in (initial or {}).items():
            self._require_layer(layer_name)
            patch = value if isinstance(value, Mapping) else self._codec.encode(value)
            self._patches[layer_name] = merge_config_patch(
                self._patches[layer_name], patch
            )
        self._value = self._compose()

    @property
    def value(self) -> T:
        return self._value

    def snapshot(self) -> ConfigSnapshot[T]:
        return ConfigSnapshot(
            value=self._value,
            patches={name: deepcopy(patch) for name, patch in self._patches.items()},
        )

    def layer_path(self, layer_name: str) -> Path | None:
        return self._require_layer(layer_name).path

    def patch(self, layer_name: str) -> dict[str, object]:
        self._require_layer(layer_name)
        return deepcopy(self._patches[layer_name])

    def reload(self) -> None:
        self._load_persistent_layers()
        self._value = self._compose()
        self._notify()

    def update(
        self,
        layer_name: str,
        patch: Mapping[str, object],
        *,
        persist: bool | None = None,
    ) -> None:
        layer = self._require_layer(layer_name)
        merged = merge_config_patch(self._patches[layer_name], patch)
        should_persist = layer.persistent if persist is None else persist
        if should_persist:
            if layer.path is None:
                raise ValueError(
                    f"Config layer {layer_name!r} requires a path for persistence"
                )
            self._store.save(layer.path, merged)
        self._patches[layer_name] = merged
        self._value = self._compose()
        self._notify()

    def replace(
        self,
        layer_name: str,
        patch: Mapping[str, object],
        *,
        persist: bool | None = None,
    ) -> None:
        self._require_layer(layer_name)
        replacement = deepcopy(dict(patch))
        layer = self._layers_by_name[layer_name]
        should_persist = layer.persistent if persist is None else persist
        if should_persist:
            if layer.path is None:
                raise ValueError(
                    f"Config layer {layer_name!r} requires a path for persistence"
                )
            self._store.save(layer.path, replacement)
        self._patches[layer_name] = replacement
        self._value = self._compose()
        self._notify()

    def subscribe(self, listener: ConfigListener[T]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return

        return unsubscribe

    def drain_issues(self) -> tuple[ConfigIssue, ...]:
        issues = tuple(self._issues)
        self._issues.clear()
        return issues

    def _load_persistent_layers(self) -> None:
        for layer in self._layers:
            if layer.path is None:
                continue
            previous = self._patches[layer.name]
            try:
                self._patches[layer.name] = deepcopy(dict(self._store.load(layer.path)))
            except Exception as exc:
                self._issues.append(
                    ConfigIssue(
                        layer=layer.name,
                        message=str(exc),
                        error=exc,
                    )
                )
                self._patches[layer.name] = previous

    def _compose(self) -> T:
        value = self._codec.default()
        for layer in self._layers:
            result = self._codec.apply(
                value,
                self._patches[layer.name],
                layer=layer.name,
            )
            value = result.value
            self._issues.extend(result.issues)
        return value

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener(self._value)

    def _require_layer(self, layer_name: str) -> ConfigLayer:
        try:
            return self._layers_by_name[layer_name]
        except KeyError as exc:
            raise KeyError(f"Unknown config layer: {layer_name}") from exc


def merge_config_patch(
    base: Mapping[str, object],
    updates: Mapping[str, object],
) -> dict[str, object]:
    merged = deepcopy(dict(base))
    for key, value in updates.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_config_patch(current, value)
        else:
            merged[key] = deepcopy(value)
    return merged


__all__ = ["LayeredConfig", "merge_config_patch"]
