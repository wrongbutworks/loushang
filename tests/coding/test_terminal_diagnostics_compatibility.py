from __future__ import annotations

from loushang.coding.ui.screen_loop import _format_terminal_diagnostics
from loushang.tui import format_terminal_diagnostics as public_formatter
from loushang.tui.terminal_diagnostics import format_terminal_diagnostics


def test_screen_loop_terminal_diagnostics_private_name_is_a_direct_alias() -> None:
    assert _format_terminal_diagnostics is format_terminal_diagnostics
    assert _format_terminal_diagnostics is public_formatter
