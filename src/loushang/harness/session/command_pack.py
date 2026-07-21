"""Standard session command parsing and execution over Product-bound ports.

This module deliberately does not own a command catalog or a session runtime.
Products register their existing command source with ``SessionCommandRuntime``
and delegate the admitted command subset here.  The bound callbacks execute
the already-composed session, lifecycle, and transcript-navigation runtimes.
"""

from __future__ import annotations

import inspect
import shlex
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from loushang.harness.commands import normalize_command_name


class StandardSessionCommandId(str, Enum):
    """Stable identifiers for shared session command mechanics."""

    SESSION = "session"
    NAME = "name"
    EXPORT = "export"
    IMPORT = "import"
    COMPACT = "compact"
    RELOAD = "reload"
    NEW = "new"
    RESUME = "resume"
    FORK = "fork"
    CLONE = "clone"
    TREE = "tree"


StandardSessionCommandDisposition = Literal[
    "completed", "unavailable", "invalid_arguments"
]
CommandPort = Callable[..., object | Awaitable[object]]
SessionNamePort = Callable[[str | None], object | Awaitable[object]]
SessionExportPort = Callable[[str | None], object | Awaitable[object]]
SessionImportPort = Callable[[str, str | None], object | Awaitable[object]]


@dataclass(frozen=True)
class StandardSessionCommandProfile:
    """Immutable Product selection of standard session command identifiers."""

    enabled_command_ids: frozenset[StandardSessionCommandId]

    @classmethod
    def standard(cls) -> "StandardSessionCommandProfile":
        return cls(frozenset(StandardSessionCommandId))

    def select(
        self, command_ids: Iterable[StandardSessionCommandId | str]
    ) -> "StandardSessionCommandProfile":
        selected = _command_ids(command_ids)
        return StandardSessionCommandProfile(self.enabled_command_ids & selected)

    def without(
        self, command_ids: Iterable[StandardSessionCommandId | str]
    ) -> "StandardSessionCommandProfile":
        return StandardSessionCommandProfile(
            self.enabled_command_ids - _command_ids(command_ids)
        )

    def includes(self, command_id: StandardSessionCommandId) -> bool:
        return command_id in self.enabled_command_ids


STANDARD_SESSION_COMMAND_PROFILE = StandardSessionCommandProfile.standard()


@dataclass(frozen=True)
class StandardSessionCommandResult:
    """Typed outcome before a Product projects it to UI or transport values."""

    command_id: StandardSessionCommandId
    disposition: StandardSessionCommandDisposition
    value: object | None = None
    error_code: str | None = None

    @classmethod
    def completed(
        cls,
        command_id: StandardSessionCommandId,
        value: object | None = None,
    ) -> "StandardSessionCommandResult":
        return cls(command_id=command_id, disposition="completed", value=value)

    @classmethod
    def unavailable(
        cls, command_id: StandardSessionCommandId
    ) -> "StandardSessionCommandResult":
        return cls(command_id=command_id, disposition="unavailable")

    @classmethod
    def invalid_arguments(
        cls,
        command_id: StandardSessionCommandId,
        error_code: str,
        value: object | None = None,
    ) -> "StandardSessionCommandResult":
        return cls(
            command_id=command_id,
            disposition="invalid_arguments",
            value=value,
            error_code=error_code,
        )


@dataclass(frozen=True)
class StandardSessionExport:
    """Product-neutral result of a completed transcript export."""

    format: Literal["html", "jsonl"]
    path: object


@dataclass
class StandardSessionCommandPorts:
    """Already-bound session operation callbacks supplied by a Product.

    Each callback delegates to an existing Product composition of Harness
    session, lifecycle, or transcript-navigation runtimes.  This command pack
    only validates arguments and chooses which admitted callback to invoke.
    """

    get_session_info: Callable[[], object] | None = None
    set_session_name: SessionNamePort | None = None
    export_html: SessionExportPort | None = None
    export_jsonl: SessionExportPort | None = None
    import_session: SessionImportPort | None = None
    compact: CommandPort | None = None
    reload: CommandPort | None = None
    new_session: CommandPort | None = None
    resume_session: CommandPort | None = None
    fork_session: CommandPort | None = None
    clone_session: CommandPort | None = None
    navigate_tree: CommandPort | None = None


def is_standard_session_command(
    invocation_name: str,
    *,
    profile: StandardSessionCommandProfile = STANDARD_SESSION_COMMAND_PROFILE,
) -> bool:
    """Return whether an invocation is selected by a standard profile."""

    command_id = _command_id(invocation_name)
    return command_id is not None and profile.includes(command_id)


async def execute_standard_session_command_async(
    invocation_name: str,
    args: str,
    ports: StandardSessionCommandPorts,
    *,
    profile: StandardSessionCommandProfile = STANDARD_SESSION_COMMAND_PROFILE,
) -> StandardSessionCommandResult | None:
    """Execute one selected standard command or return ``None`` when unhandled.

    Product-local commands stay unhandled.  Exceptions from a bound operation
    deliberately propagate: lifecycle, compaction, and navigation runtimes
    retain their established rollback and failure behavior.
    """

    command_id = _command_id(invocation_name)
    if command_id is None or not profile.includes(command_id):
        return None

    match command_id:
        case StandardSessionCommandId.SESSION:
            if ports.get_session_info is None:
                return StandardSessionCommandResult.unavailable(command_id)
            return StandardSessionCommandResult.completed(
                command_id, ports.get_session_info()
            )
        case StandardSessionCommandId.NAME:
            if ports.set_session_name is None:
                return StandardSessionCommandResult.unavailable(command_id)
            name = args.strip() or None
            await _resolve(ports.set_session_name(name))
            return StandardSessionCommandResult.completed(command_id, name)
        case StandardSessionCommandId.EXPORT:
            raw_path = args.strip() or None
            export_format: Literal["html", "jsonl"] = (
                "jsonl"
                if raw_path is not None and raw_path.lower().endswith(".jsonl")
                else "html"
            )
            export_port = (
                ports.export_jsonl if export_format == "jsonl" else ports.export_html
            )
            if export_port is None:
                return StandardSessionCommandResult.unavailable(command_id)
            path = await _resolve(export_port(raw_path))
            return StandardSessionCommandResult.completed(
                command_id,
                StandardSessionExport(format=export_format, path=path),
            )
        case StandardSessionCommandId.IMPORT:
            if ports.import_session is None:
                return StandardSessionCommandResult.unavailable(command_id)
            tokens = _split_args(args)
            if not tokens:
                return StandardSessionCommandResult.invalid_arguments(
                    command_id, "missing_import_path"
                )
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(
                    ports.import_session(
                        tokens[0], tokens[1] if len(tokens) > 1 else None
                    )
                ),
            )
        case StandardSessionCommandId.COMPACT:
            if ports.compact is None:
                return StandardSessionCommandResult.unavailable(command_id)
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.compact(args.strip() or None)),
            )
        case StandardSessionCommandId.RELOAD:
            if ports.reload is None:
                return StandardSessionCommandResult.unavailable(command_id)
            await _resolve(ports.reload())
            return StandardSessionCommandResult.completed(command_id)
        case StandardSessionCommandId.NEW:
            if ports.new_session is None:
                return StandardSessionCommandResult.unavailable(command_id)
            tokens = _split_args(args)
            options: dict[str, object] = {}
            if tokens:
                options["cwd"] = tokens[0]
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.new_session(options or None)),
            )
        case StandardSessionCommandId.RESUME:
            if ports.resume_session is None:
                return StandardSessionCommandResult.unavailable(command_id)
            tokens = _split_args(args)
            if not tokens:
                return StandardSessionCommandResult.invalid_arguments(
                    command_id, "missing_reference"
                )
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.resume_session(tokens[0], None)),
            )
        case StandardSessionCommandId.FORK:
            if ports.fork_session is None:
                return StandardSessionCommandResult.unavailable(command_id)
            tokens = _split_args(args)
            if not tokens:
                return StandardSessionCommandResult.invalid_arguments(
                    command_id, "missing_record_id"
                )
            options: dict[str, object] = {}
            if len(tokens) > 1:
                if tokens[1] not in {"before", "at"}:
                    return StandardSessionCommandResult.invalid_arguments(
                        command_id, "invalid_fork_position", tokens[1]
                    )
                options["position"] = tokens[1]
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.fork_session(tokens[0], options or None)),
            )
        case StandardSessionCommandId.CLONE:
            if ports.clone_session is None:
                return StandardSessionCommandResult.unavailable(command_id)
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.clone_session()),
            )
        case StandardSessionCommandId.TREE:
            if ports.navigate_tree is None:
                return StandardSessionCommandResult.unavailable(command_id)
            tokens = _split_args(args)
            if not tokens:
                return StandardSessionCommandResult.invalid_arguments(
                    command_id, "missing_record_id"
                )
            options = _parse_tree_options(tokens[1:])
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.navigate_tree(tokens[0], options or None)),
            )


def _command_id(invocation_name: str) -> StandardSessionCommandId | None:
    if not isinstance(invocation_name, str):
        return None
    try:
        return StandardSessionCommandId(normalize_command_name(invocation_name))
    except ValueError:
        return None


def _command_ids(
    command_ids: Iterable[StandardSessionCommandId | str],
) -> frozenset[StandardSessionCommandId]:
    if isinstance(command_ids, str):
        raise TypeError("command ids must be an iterable, not a string")
    ids: set[StandardSessionCommandId] = set()
    for command_id in command_ids:
        try:
            ids.add(StandardSessionCommandId(command_id))
        except ValueError as exc:
            raise ValueError(
                f"unknown standard session command: {command_id!r}"
            ) from exc
    return frozenset(ids)


async def _resolve(value: object | Awaitable[object]) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _split_args(args: str) -> list[str]:
    try:
        return shlex.split(args)
    except ValueError:
        return args.split()


def _parse_tree_options(tokens: list[str]) -> dict[str, object]:
    options: dict[str, object] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--summarize":
            options["summarize"] = True
        elif token in {"--label", "-l"} and index + 1 < len(tokens):
            index += 1
            options["label"] = tokens[index]
        elif token == "--replace-instructions":
            options["replace_instructions"] = True
        elif token in {"--instructions", "--custom-instructions"} and index + 1 < len(
            tokens
        ):
            index += 1
            options["custom_instructions"] = tokens[index]
        index += 1
    return options


__all__ = [
    "STANDARD_SESSION_COMMAND_PROFILE",
    "StandardSessionCommandDisposition",
    "StandardSessionExport",
    "StandardSessionCommandId",
    "StandardSessionCommandPorts",
    "StandardSessionCommandProfile",
    "StandardSessionCommandResult",
    "execute_standard_session_command_async",
    "is_standard_session_command",
]
