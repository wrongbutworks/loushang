from __future__ import annotations

from loushang.harness.capabilities.commands import CommandCatalog, CommandDescriptor
from loushang.harness.command_composition import (
    MixedCommandCatalog,
    MixedCommandCatalogPorts,
    MixedCommandCatalogProfile,
)
from loushang.harness.commands import CommandDef, CommandKind


def _command(name: str, *, kind: CommandKind = CommandKind.LOCAL_UI) -> CommandDef:
    return CommandDef(
        id=f"test.{kind.value}.{name}",
        name=name,
        kind=kind,
    )


def _session_command(descriptor: CommandDescriptor[object]) -> CommandDef:
    return CommandDef(
        id=f"test.session.{descriptor.effective_invocation_name}",
        name=descriptor.effective_invocation_name,
        kind=CommandKind.SESSION,
        description=descriptor.description,
        source=descriptor.source,
        aliases=descriptor.aliases,
    )


def _profile() -> MixedCommandCatalogProfile:
    settings = _command("settings")
    model = _command("model")
    return MixedCommandCatalogProfile(
        local_commands_by_name={
            settings.name: settings,
            model.name: model,
        },
        local_commands_by_route={"settings_route": settings},
        local_commands_accepting_args=frozenset({"model"}),
    )


def test_mixed_catalog_routes_and_validates_product_local_commands() -> None:
    catalog: MixedCommandCatalog[object] = MixedCommandCatalog(profile=_profile())

    assert catalog.local_for_route("settings_route") == _command("settings")
    assert catalog.local_for_route("unknown") is None
    assert catalog.lookup("/settings") == _command("settings")
    assert catalog.lookup("/settings extra") is None
    assert catalog.lookup("/model provider/model") == _command("model")
    assert catalog.lookup("plain text") is None


def test_mixed_catalog_preserves_session_resolution_and_invocation_payload() -> None:
    descriptors: CommandCatalog[object] = CommandCatalog(
        (
            CommandDescriptor(
                name="deploy",
                invocation_name="deploy",
                description="old",
                source="builtin",
                aliases=("ship",),
                precedence=1,
            ),
            CommandDescriptor(
                name="deploy",
                invocation_name="deploy",
                description="new",
                source="extension",
                aliases=("release",),
                precedence=2,
            ),
        )
    )
    catalog = MixedCommandCatalog(
        profile=_profile(),
        ports=MixedCommandCatalogPorts(
            session_catalog=lambda: descriptors,
            session_command=_session_command,
        ),
    )

    match = catalog.session_match("/release production")

    assert match is not None
    assert match.command.description == "new"
    assert match.command.source == "extension"
    assert match.invocation_name == "release"
    assert match.args == "production"


def test_mixed_catalog_lists_session_commands_then_unshadowed_locals() -> None:
    descriptors: CommandCatalog[object] = CommandCatalog(
        (
            CommandDescriptor(
                name="settings",
                description="session settings",
                source="session",
            ),
            CommandDescriptor(
                name="report",
                description="report",
                source="session",
            ),
        )
    )
    catalog = MixedCommandCatalog(
        profile=_profile(),
        ports=MixedCommandCatalogPorts(
            session_catalog=lambda: descriptors,
            session_command=_session_command,
        ),
    )

    assert [command.name for command in catalog.commands()] == [
        "settings",
        "report",
        "model",
    ]
    assert catalog.lookup("/settings") == _command("settings")
