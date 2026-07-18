"""Compatibility facade for :mod:`loushang.coding.testing.tui.fakes`."""

from loushang.coding.testing.tui.fakes import (
    AppleShiftEnterTerminalContext,
    ModelPlaybackSession,
    RecordingTerminalContext,
    RecordingTerminalMode,
    SessionCommandPlaybackSession,
    recording_drain,
)

__all__ = [
    "AppleShiftEnterTerminalContext",
    "ModelPlaybackSession",
    "RecordingTerminalContext",
    "RecordingTerminalMode",
    "SessionCommandPlaybackSession",
    "recording_drain",
]
