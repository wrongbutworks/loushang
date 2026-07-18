"""Compatibility facade for :mod:`loushang.coding.testing.tui.playback`."""

from __future__ import annotations

from loushang.coding.testing.tui import playback as _impl
from loushang.coding.testing.tui.playback import (
    ScreenTuiAbortHandler,
    ScreenTuiHandler,
    ScreenTuiInputPlayback,
    ScreenTuiInputPlaybackResult,
    ScreenTuiInputScenario,
    ScreenTuiLoopArtifacts,
    ScreenTuiLoopPlayback,
    ScreenTuiLoopPlaybackResult,
    ScreenTuiLoopScenario,
    ScreenTuiScenario,
)

__all__ = [
    "ScreenTuiAbortHandler",
    "ScreenTuiHandler",
    "ScreenTuiInputPlayback",
    "ScreenTuiInputPlaybackResult",
    "ScreenTuiInputScenario",
    "ScreenTuiLoopArtifacts",
    "ScreenTuiLoopPlayback",
    "ScreenTuiLoopPlaybackResult",
    "ScreenTuiLoopScenario",
    "ScreenTuiScenario",
]


def __getattr__(name: str) -> object:
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_impl)))
