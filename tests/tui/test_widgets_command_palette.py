from __future__ import annotations

from typing import get_args

from loushang.tui import CommandPalette, CommandPaletteItem
from loushang.tui.input import InputIntentKind


def intent_tuple(intent: object) -> tuple[str, str, str]:
    return (
        str(getattr(intent, "kind", "")),
        str(getattr(intent, "text", "")),
        str(getattr(intent, "note", "")),
    )


def intent_tuples(intents: object) -> tuple[tuple[str, str, str], ...]:
    if isinstance(intents, tuple):
        return tuple(intent_tuple(intent) for intent in intents)
    return (intent_tuple(intents),)


def test_command_palette_item_disabled_defaults_to_false() -> None:
    assert CommandPaletteItem("deploy").disabled is False
    assert CommandPaletteItem("archive", disabled=True).disabled is True


def test_command_palette_intent_kinds_are_declared() -> None:
    kinds = get_args(InputIntentKind)

    assert "command_select" in kinds
    assert "command_cancel" in kinds


def test_existing_coding_palette_adapter_keeps_disabled_out_of_scope() -> None:
    from loushang.coding.ui.native_surfaces import _palette_items

    items = _palette_items(
        CommandPalette(
            (
                CommandPaletteItem(
                    value="archive",
                    label="Archive release",
                    description="unavailable",
                    disabled=True,
                ),
            )
        )
    )

    assert len(items) == 1
    assert items[0].selected_value == "archive"
    assert not hasattr(items[0], "disabled")
