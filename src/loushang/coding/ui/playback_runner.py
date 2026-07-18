"""Compatibility CLI for :mod:`loushang.coding.testing.tui.runner`."""

from __future__ import annotations

from collections.abc import Sequence

from loushang.coding.testing.tui.runner import (
    DEFAULT_SUITE,
    ScreenPlaybackScenarioResult,
    ScreenPlaybackScenarioSpec,
    ScreenPlaybackSuite,
    run_playback_cli,
    run_playback_scenarios,
)

__all__ = [
    "DEFAULT_SUITE",
    "ScreenPlaybackScenarioResult",
    "ScreenPlaybackScenarioSpec",
    "ScreenPlaybackSuite",
    "run_playback_cli",
    "run_playback_scenarios",
]


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(run_playback_cli(argv))


if __name__ == "__main__":
    main()
