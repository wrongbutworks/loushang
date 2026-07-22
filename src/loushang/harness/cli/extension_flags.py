"""Shared discovery and application of extension-provided CLI flags."""

from __future__ import annotations

from collections.abc import Mapping


def collect_extension_flags(session: object) -> dict[str, object]:
    """Collect named flags from an injected extension runner."""

    runner = getattr(session, "extension_runner", None)
    getter = getattr(runner, "get_flags", None)
    if not callable(getter):
        return {}
    try:
        flags = getter()
    except Exception:
        return {}
    collected: dict[str, object] = {}
    for flag in flags:
        name = getattr(flag, "name", None)
        if isinstance(name, str) and name:
            collected[name] = flag
    return collected


def apply_extension_flag_values(
    session: object,
    values: Mapping[str, bool | str],
) -> None:
    """Apply parsed values through the extension runner, if available."""

    if not values:
        return
    runner = getattr(session, "extension_runner", None)
    setter = getattr(runner, "set_flag_value", None)
    if not callable(setter):
        return
    for name, value in values.items():
        setter(name, value)


__all__ = ["apply_extension_flag_values", "collect_extension_flags"]
