from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from loushang.coding.commands.profile import CODING_COMMAND_CATALOG_PROFILE
from loushang.harness.commands import (
    CommandCatalog,
    CommandDef,
    CommandDescriptor,
    CommandEffect,
    CommandEffectKind,
    CommandKind,
    MixedCommandCatalog,
    MixedCommandCatalogPorts,
)

SessionCommandsProvider = Callable[[], Iterable[object]]


class CodingCommandCatalog:
    def __init__(
        self, *, session_commands: SessionCommandsProvider | None = None
    ) -> None:
        self._session_commands = session_commands
        self._catalog = MixedCommandCatalog(
            profile=CODING_COMMAND_CATALOG_PROFILE,
            ports=MixedCommandCatalogPorts(
                session_catalog=(
                    self._session_catalog if session_commands is not None else None
                ),
                session_command=(
                    _session_command_def if session_commands is not None else None
                ),
            ),
        )

    def commands(self) -> tuple[CommandDef, ...]:
        return self._catalog.commands()

    def effect_for_route(self, route: object, intent: object) -> CommandEffect | None:
        route_value = _route_value(route)
        command = self._catalog.local_for_route(route_value)
        if command is not None:
            return CommandEffect(kind=CommandEffectKind.LOCAL_UI, command=command)
        if route_value == "dispatch":
            text = _string_attr(intent, "text")
            if text is not None:
                return self._session_effect_for_text(text)
        return None

    def lookup(self, text: str) -> CommandDef | None:
        return self._catalog.lookup(text)

    def _session_effect_for_text(self, text: str) -> CommandEffect | None:
        match = self._catalog.session_match(text)
        if match is None:
            return None
        return CommandEffect(
            kind=CommandEffectKind.SESSION,
            command=match.command,
            payload={"invocation_name": match.invocation_name, "args": match.args},
        )

    def _session_catalog(self) -> CommandCatalog[object]:
        if self._session_commands is None:
            return CommandCatalog()
        raw_commands = self._session_commands()
        if not isinstance(raw_commands, Iterable):
            return CommandCatalog()
        return CommandCatalog(
            descriptor
            for raw_command in raw_commands
            if (descriptor := _session_command_descriptor(raw_command)) is not None
        )


def _route_value(route: object) -> str:
    value = getattr(route, "value", route)
    return value if isinstance(value, str) else str(value)


def _string_attr(value: Any, name: str) -> str | None:
    raw = getattr(value, name, None)
    return raw if isinstance(raw, str) and raw else None


def _session_command_descriptor(
    raw_command: object,
) -> CommandDescriptor[object] | None:
    name = _string_attr(raw_command, "name")
    invocation_name = _string_attr(raw_command, "invocation_name") or name
    if invocation_name is None:
        return None
    precedence = getattr(raw_command, "precedence", 0)
    if not isinstance(precedence, int) or isinstance(precedence, bool):
        precedence = 0
    aliases = getattr(raw_command, "aliases", ())
    if not isinstance(aliases, (tuple, list)):
        aliases = ()
    return CommandDescriptor(
        name=name or invocation_name,
        description=_string_attr(raw_command, "description"),
        source=_string_attr(raw_command, "source") or "session",
        source_info=getattr(raw_command, "source_info", None),
        invocation_name=invocation_name,
        aliases=tuple(alias for alias in aliases if isinstance(alias, str) and alias),
        conflict_group=_string_attr(raw_command, "conflict_group"),
        argument_hint=_string_attr(raw_command, "argument_hint"),
        precedence=precedence,
    )


def _session_command_def(descriptor: CommandDescriptor[object]) -> CommandDef:
    normalized = descriptor.effective_invocation_name
    return CommandDef(
        id=f"coding.session.{normalized}",
        name=normalized,
        kind=CommandKind.SESSION,
        description=descriptor.description,
        source=descriptor.source,
        aliases=descriptor.aliases,
        argument_hint=descriptor.argument_hint,
    )


__all__ = ["CodingCommandCatalog", "SessionCommandsProvider"]
