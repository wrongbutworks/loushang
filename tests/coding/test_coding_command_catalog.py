from __future__ import annotations

from types import SimpleNamespace


def test_coding_command_catalog_classifies_local_and_session_commands() -> None:
    from loushang.coding.commands.catalog import CodingCommandCatalog
    from loushang.coding.interaction.intent import PromptIntent, SettingsIntent
    from loushang.coding.interaction.routing import PromptRoute
    from loushang.harness.commands import CommandEffectKind, CommandKind

    catalog = CodingCommandCatalog(
        session_commands=lambda: [
            SimpleNamespace(
                name="name",
                invocation_name="name",
                description="Set session display name",
                source="builtin",
                argument_hint="<name>",
            )
        ]
    )

    settings_effect = catalog.effect_for_route(PromptRoute.SETTINGS, SettingsIntent())
    assert settings_effect is not None
    assert settings_effect.kind is CommandEffectKind.LOCAL_UI
    assert settings_effect.command.kind is CommandKind.LOCAL_UI
    assert settings_effect.command.id == "coding.ui.settings"

    name_effect = catalog.effect_for_route(PromptRoute.DISPATCH, PromptIntent("/name Project Alpha"))
    assert name_effect is not None
    assert name_effect.kind is CommandEffectKind.SESSION
    assert name_effect.command.kind is CommandKind.SESSION
    assert name_effect.command.name == "name"
    assert name_effect.payload == {"invocation_name": "name", "args": "Project Alpha"}


def test_coding_command_catalog_leaves_plain_prompts_and_queue_routes_unowned() -> None:
    from loushang.coding.commands.catalog import CodingCommandCatalog
    from loushang.coding.interaction.intent import FollowUpIntent, PromptIntent
    from loushang.coding.interaction.routing import PromptRoute

    catalog = CodingCommandCatalog(session_commands=lambda: [])

    assert catalog.effect_for_route(PromptRoute.DISPATCH, PromptIntent("hello")) is None
    assert catalog.effect_for_route(PromptRoute.STEER, PromptIntent("steer")) is None
    assert catalog.effect_for_route(PromptRoute.FOLLOW_UP, FollowUpIntent("later")) is None


def test_coding_command_catalog_preserves_local_command_argument_rules() -> None:
    from loushang.coding.commands.catalog import CodingCommandCatalog
    from loushang.harness.commands import CommandKind

    catalog = CodingCommandCatalog(session_commands=lambda: [])

    terminal = catalog.lookup("/terminal")
    assert terminal is not None
    assert terminal.kind is CommandKind.LOCAL_UI

    assert catalog.lookup("/model kimi").name == "model"
    assert catalog.lookup("/commands model").name == "commands"
    assert catalog.lookup("/config").name == "config"
    assert catalog.lookup("/terminal extra") is None


def test_coding_command_catalog_lists_local_and_session_commands_once() -> None:
    from loushang.coding.commands.catalog import CodingCommandCatalog
    from loushang.harness.commands import CommandKind

    catalog = CodingCommandCatalog(
        session_commands=lambda: [
            SimpleNamespace(name="report", description="Session report", source="builtin"),
            SimpleNamespace(name="deploy", description="Deploy app", source="extension"),
        ]
    )

    commands = catalog.commands()
    by_name = {command.name: command for command in commands}

    assert len([command for command in commands if command.name == "report"]) == 1
    assert by_name["report"].kind is CommandKind.SESSION
    assert by_name["report"].source == "builtin"
    assert by_name["deploy"].kind is CommandKind.SESSION
    assert by_name["deploy"].source == "extension"
    assert by_name["settings"].kind is CommandKind.LOCAL_UI
    assert by_name["config"].kind is CommandKind.LOCAL_UI
