from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from loushang.tui.core import RenderConstraints, RenderResult
from loushang.tui.theme import ThemeResolver

ToastKind = Literal["info", "success", "warning", "danger"]
_NowMs = Callable[[], int]
_VALID_KINDS = frozenset({"info", "success", "warning", "danger"})

__all__ = ["Toast", "ToastKind", "ToastStack"]


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


@dataclass(frozen=True, slots=True)
class Toast:
    message: str
    title: str = ""
    kind: ToastKind = "info"
    value: str = ""
    duration_ms: int | None = 4000
    created_at_ms: int | None = None
    dismissible: bool = True


@dataclass(slots=True)
class ToastStack:
    toasts: Sequence[Toast] = ()
    max_visible: int = 3
    newest_on_top: bool = True
    empty_height: int = 0
    theme: ThemeResolver | None = None
    now_ms: _NowMs = _monotonic_ms
    _next_generated_index: int = field(default=1, init=False, repr=False)

    def __post_init__(self) -> None:
        self.empty_height = max(0, self.empty_height)
        self.toasts = self._normalize_batch(tuple(self.toasts))

    def _normalize_batch(self, toasts: tuple[Toast, ...]) -> tuple[Toast, ...]:
        now_ms = self.now_ms() if any(toast.created_at_ms is None for toast in toasts) else None
        existing: set[str] = set()
        normalized: list[Toast] = []
        for toast in toasts:
            normalized.append(self._normalize_toast(toast, now_ms=now_ms, existing_values=existing))
        return tuple(normalized)

    def _normalize_toast(self, toast: Toast, *, now_ms: int | None, existing_values: set[str]) -> Toast:
        self._validate_toast(toast)
        value = toast.value or self._next_generated_value(existing_values)
        if value in existing_values:
            raise ValueError(f"duplicate Toast value: {value!r}")
        existing_values.add(value)
        if toast.created_at_ms is None:
            if now_ms is None:
                raise AssertionError("now_ms is required for Toast without created_at_ms")
            created_at_ms = now_ms
        else:
            created_at_ms = toast.created_at_ms
        return replace(toast, value=value, created_at_ms=created_at_ms)

    def _next_generated_value(self, existing_values: set[str]) -> str:
        stored_values = {toast.value for toast in self.toasts}
        while True:
            value = f"toast-{self._next_generated_index}"
            self._next_generated_index += 1
            if value not in existing_values and value not in stored_values:
                return value

    def _validate_toast(self, toast: Toast) -> None:
        if toast.kind not in _VALID_KINDS:
            raise ValueError(f"unknown Toast kind: {toast.kind!r}")
        if toast.duration_ms is not None and toast.duration_ms < 0:
            raise ValueError("Toast duration_ms must be non-negative or None")

    def all_toasts(self) -> tuple[Toast, ...]:
        return tuple(self.toasts)

    def push(self, toast: Toast | str, **overrides: object) -> str:
        if isinstance(toast, str):
            if "message" in overrides:
                raise TypeError("Toast message cannot be overridden when pushing a string")
            candidate = Toast(toast, **overrides)
        elif isinstance(toast, Toast):
            candidate = replace(toast, **overrides) if overrides else toast
        else:
            raise TypeError("push() expects Toast or str")
        existing = {item.value for item in self.toasts}
        now_ms = self.now_ms() if candidate.created_at_ms is None else None
        normalized = self._normalize_toast(candidate, now_ms=now_ms, existing_values=existing)
        self.toasts = (*tuple(self.toasts), normalized)
        return normalized.value

    def visible_toasts(self) -> tuple[Toast, ...]:
        return tuple(self.toasts)

    def prune_expired(self) -> int:
        return 0

    def dismiss(self, value: str) -> bool:
        for toast in self.toasts:
            if toast.value == value and toast.dismissible:
                self.toasts = tuple(item for item in self.toasts if item.value != value)
                return True
            if toast.value == value:
                return False
        return False

    def dismiss_oldest(self) -> bool:
        return False

    def clear(self) -> None:
        self.toasts = ()

    def render(self, constraints: RenderConstraints) -> RenderResult:
        return RenderResult.from_lines([], constraints=constraints)
