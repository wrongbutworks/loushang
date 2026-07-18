"""Coding binding for product-neutral terminal playback scenarios."""

from __future__ import annotations

from loushang.coding.testing.tui.scenario_binding import CODING_SCENARIO_FACTORY
from loushang.harnesstui.testing.scenarios.terminal import terminal_scenarios

TERMINAL_SCENARIOS = terminal_scenarios(CODING_SCENARIO_FACTORY)

__all__ = ["TERMINAL_SCENARIOS"]
