"""Coding-owned local command vocabulary and product routing."""

from __future__ import annotations

from loushang.harness.commands import (
    CommandDef,
    CommandKind,
    LocalCommandCatalogProfile,
)

_CODING_LOCAL_COMMANDS = {
    "model": CommandDef(
        id="coding.ui.model",
        name="model",
        kind=CommandKind.LOCAL_UI,
        description="Select model",
        source="local",
    ),
    "models": CommandDef(
        id="coding.ui.models",
        name="models",
        kind=CommandKind.LOCAL_UI,
        description="Show available models",
        source="local",
    ),
    "command": CommandDef(
        id="coding.ui.command",
        name="command",
        kind=CommandKind.LOCAL_UI,
        description="Select command",
        source="local",
    ),
    "commands": CommandDef(
        id="coding.ui.commands",
        name="commands",
        kind=CommandKind.LOCAL_UI,
        description="Show commands",
        source="local",
    ),
    "hotkeys": CommandDef(
        id="coding.ui.hotkeys",
        name="hotkeys",
        kind=CommandKind.LOCAL_UI,
        description="Show keyboard shortcuts",
        source="local",
    ),
    "settings": CommandDef(
        id="coding.ui.settings",
        name="settings",
        kind=CommandKind.LOCAL_UI,
        description="Open settings",
        source="local",
    ),
    "config": CommandDef(
        id="coding.ui.config",
        name="config",
        kind=CommandKind.LOCAL_UI,
        description="Open settings",
        source="local",
    ),
    "terminal": CommandDef(
        id="coding.ui.terminal",
        name="terminal",
        kind=CommandKind.LOCAL_UI,
        description="Show terminal diagnostics",
        source="local",
    ),
}

CODING_COMMAND_CATALOG_PROFILE = LocalCommandCatalogProfile(
    local_commands_by_name=_CODING_LOCAL_COMMANDS,
    local_command_names_by_route={
        "model_select": "model",
        "models": "models",
        "command_select": "command",
        "commands": "commands",
        "hotkeys": "hotkeys",
        "settings": "settings",
        "config": "config",
        "terminal": "terminal",
    },
    local_commands_accepting_args=frozenset({"command", "commands", "model", "models"}),
)


__all__ = ["CODING_COMMAND_CATALOG_PROFILE"]
