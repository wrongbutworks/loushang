"""Product-neutral composition of local and session command catalogs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from loushang.harness.capabilities.commands import (
    CommandCatalog,
    CommandDescriptor,
    split_slash_command,
)
from loushang.harness.commands import CommandDef

SourceInfoT = TypeVar("SourceInfoT")


@dataclass(frozen=True, slots=True)
class MixedCommandCatalogProfile:
    """Product-owned local command definitions and argument policy."""

    local_commands_by_name: Mapping[str, CommandDef]
    local_commands_by_route: Mapping[str, CommandDef]
    local_commands_accepting_args: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class MixedCommandCatalogPorts(Generic[SourceInfoT]):
    """Product adapters for acquiring and projecting session commands."""

    session_catalog: Callable[[], CommandCatalog[SourceInfoT]] | None = None
    session_command: Callable[[CommandDescriptor[SourceInfoT]], CommandDef] | None = (
        None
    )


@dataclass(frozen=True, slots=True)
class MixedCommandMatch:
    command: CommandDef
    invocation_name: str
    args: str


class MixedCommandCatalog(Generic[SourceInfoT]):
    """Compose local definitions with an optional resolved session catalog."""

    def __init__(
        self,
        *,
        profile: MixedCommandCatalogProfile,
        ports: MixedCommandCatalogPorts[SourceInfoT] | None = None,
    ) -> None:
        self.profile = profile
        self.ports = ports or MixedCommandCatalogPorts()

    def commands(self) -> tuple[CommandDef, ...]:
        session_commands = tuple(
            self._project_session_command(descriptor)
            for descriptor in self._session_catalog().commands()
        )
        session_names = {command.name for command in session_commands}
        local_commands = tuple(
            command
            for name, command in self.profile.local_commands_by_name.items()
            if name not in session_names
        )
        return (*session_commands, *local_commands)

    def local_for_route(self, route_value: str) -> CommandDef | None:
        return self.profile.local_commands_by_route.get(route_value)

    def lookup(self, text: str) -> CommandDef | None:
        local_command = self.local_for_text(text)
        if local_command is not None:
            return local_command
        match = self.session_match(text)
        return match.command if match is not None else None

    def local_for_text(self, text: str) -> CommandDef | None:
        parsed = split_slash_command(text.strip())
        if parsed is None:
            return None
        invocation_name, args = parsed
        name = invocation_name.removeprefix("/")
        command = self.profile.local_commands_by_name.get(name)
        if command is None:
            return None
        if args and name not in self.profile.local_commands_accepting_args:
            return None
        return command

    def session_match(self, text: str) -> MixedCommandMatch | None:
        parsed = split_slash_command(text.strip())
        if parsed is None or self.ports.session_catalog is None:
            return None
        invocation_name, args = parsed
        descriptor = self._session_catalog().lookup(invocation_name)
        if descriptor is None:
            return None
        return MixedCommandMatch(
            command=self._project_session_command(descriptor),
            invocation_name=invocation_name,
            args=args,
        )

    def _session_catalog(self) -> CommandCatalog[SourceInfoT]:
        if self.ports.session_catalog is None:
            return CommandCatalog()
        return self.ports.session_catalog()

    def _project_session_command(
        self,
        descriptor: CommandDescriptor[SourceInfoT],
    ) -> CommandDef:
        if self.ports.session_command is None:
            raise TypeError("Session command projection port is required")
        return self.ports.session_command(descriptor)


__all__ = [
    "MixedCommandCatalog",
    "MixedCommandCatalogPorts",
    "MixedCommandCatalogProfile",
    "MixedCommandMatch",
]
