"""Standard session command parsing and execution over Product-bound ports.

This module deliberately does not own a command catalog or a session runtime.
Products register their existing command source with ``SessionCommandRuntime``
and delegate the admitted command subset here.  The bound callbacks execute
the already-composed session, lifecycle, and transcript-navigation runtimes.
"""

from __future__ import annotations

import inspect
import shlex
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from typing import Literal

from loushang.harness.commands import SessionCommandDescriptor, normalize_command_name
from loushang.harness.resources.source import create_source_info


class StandardSessionCommandId(str, Enum):
    """Stable identifiers for shared session command mechanics."""

    SESSION = "session"
    RENAME = "rename"
    EXPORT = "export"
    IMPORT = "import"
    COMPACT = "compact"
    RELOAD = "reload"
    NEW = "new"
    RESUME = "resume"
    DELETE = "delete"
    FORK = "fork"
    CLONE = "clone"
    TREE = "tree"
    TOOLS = "tools"
    EXTENSIONS = "extensions"
    COPY = "copy"
    CHANGELOG = "changelog"


@dataclass(frozen=True)
class StandardSessionCommandDefinition:
    """Shared slash-command metadata for one standard session operation."""

    command_id: StandardSessionCommandId
    description: str
    argument_hint: str | None = None

    @property
    def name(self) -> str:
        return self.command_id.value


STANDARD_SESSION_COMMANDS: tuple[StandardSessionCommandDefinition, ...] = (
    StandardSessionCommandDefinition(
        StandardSessionCommandId.EXPORT,
        "Export session (HTML default, or specify path: .html/.jsonl)",
    ),
    StandardSessionCommandDefinition(
        StandardSessionCommandId.IMPORT,
        "Import and resume a session from a JSONL file",
    ),
    StandardSessionCommandDefinition(
        StandardSessionCommandId.COPY,
        "Copy an assistant message to clipboard",
    ),
    StandardSessionCommandDefinition(
        StandardSessionCommandId.RENAME,
        "Rename the current session",
        "<name>",
    ),
    StandardSessionCommandDefinition(StandardSessionCommandId.SESSION, "Show session info and stats"),
    StandardSessionCommandDefinition(StandardSessionCommandId.CHANGELOG, "Show changelog entries"),
    StandardSessionCommandDefinition(StandardSessionCommandId.FORK, "Create a new fork from a previous user message"),
    StandardSessionCommandDefinition(StandardSessionCommandId.CLONE, "Duplicate the current session at the current position"),
    StandardSessionCommandDefinition(StandardSessionCommandId.TREE, "Navigate session tree (switch branches)"),
    StandardSessionCommandDefinition(StandardSessionCommandId.TOOLS, "Show or update active tools for this session"),
    StandardSessionCommandDefinition(StandardSessionCommandId.EXTENSIONS, "Show loaded extensions and diagnostics"),
    StandardSessionCommandDefinition(
        StandardSessionCommandId.NEW,
        "Start a new session in the current context",
    ),
    StandardSessionCommandDefinition(StandardSessionCommandId.COMPACT, "Manually compact the session context"),
    StandardSessionCommandDefinition(StandardSessionCommandId.RESUME, "Resume a different session"),
    StandardSessionCommandDefinition(
        StandardSessionCommandId.DELETE,
        "Delete a previous session",
    ),
    StandardSessionCommandDefinition(StandardSessionCommandId.RELOAD, "Reload keybindings, extensions, skills, prompts, and themes"),
)


def list_standard_session_command_descriptors() -> list[SessionCommandDescriptor]:
    source_info = create_source_info(
        "<builtin>", source="builtin", scope="project", origin="harness"
    )
    return [
        SessionCommandDescriptor(
            name=definition.name,
            description=definition.description,
            source="builtin",
            source_info=source_info,
            argument_hint=definition.argument_hint,
        )
        for definition in STANDARD_SESSION_COMMANDS
    ]


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
    get_active_tool_names: Callable[[], list[str]] | None = None
    get_all_tools: Callable[[], list[object]] | None = None
    set_active_tools: Callable[[list[str]], object | Awaitable[object]] | None = None
    get_default_active_tool_names: Callable[[], list[str]] | None = None
    get_extensions: Callable[[], list[object]] | None = None
    get_recent_assistant_texts: Callable[[], tuple[str, ...]] | None = None
    get_last_assistant_text: Callable[[], str | None] | None = None
    copy_text: Callable[[str], object] | None = None
    get_changelog: CommandPort | None = None


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
        case StandardSessionCommandId.RENAME:
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
            if args.strip():
                return StandardSessionCommandResult.invalid_arguments(
                    command_id, "unexpected_arguments"
                )
            return StandardSessionCommandResult.completed(
                command_id,
                await _resolve(ports.new_session()),
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
        case StandardSessionCommandId.DELETE:
            if args.strip():
                return StandardSessionCommandResult.invalid_arguments(
                    command_id, "unexpected_arguments"
                )
            return StandardSessionCommandResult.unavailable(command_id)
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
        case StandardSessionCommandId.TOOLS:
            return await _execute_tools_command(args, ports)
        case StandardSessionCommandId.EXTENSIONS:
            return await _execute_extensions_command(args, ports)
        case StandardSessionCommandId.COPY:
            return _execute_copy_command(args, ports)
        case StandardSessionCommandId.CHANGELOG:
            if ports.get_changelog is None:
                return StandardSessionCommandResult.unavailable(command_id)
            return StandardSessionCommandResult.completed(
                command_id, await _resolve(ports.get_changelog(args))
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


async def _execute_tools_command(
    args: str, ports: StandardSessionCommandPorts
) -> StandardSessionCommandResult:
    command_id = StandardSessionCommandId.TOOLS
    if ports.get_active_tool_names is None or ports.get_all_tools is None:
        return StandardSessionCommandResult.unavailable(command_id)
    active_tools = list(ports.get_active_tool_names())
    available_tools = _available_tool_entries(ports.get_all_tools(), active_tools)
    available_names = [
        name for entry in available_tools if isinstance(name := entry.get("name"), str)
    ]
    tokens = _split_args(args.strip()) if args.strip() else []
    if not tokens:
        return StandardSessionCommandResult.completed(
            command_id, _tools_result(active_tools, available_tools)
        )
    action = tokens[0]
    if action == "reset":
        if len(tokens) != 1 or ports.set_active_tools is None:
            return StandardSessionCommandResult.invalid_arguments(
                command_id, "invalid_tools_arguments"
            )
        if ports.get_default_active_tool_names is None:
            return StandardSessionCommandResult.unavailable(command_id)
        next_tools = _filter_available_tools(
            ports.get_default_active_tool_names(), available_names
        )
    else:
        if action not in {"on", "off", "only"} or ports.set_active_tools is None:
            return StandardSessionCommandResult.invalid_arguments(
                command_id, "invalid_tools_arguments"
            )
        requested = _parse_tool_names(tokens[1:])
        if not requested:
            return StandardSessionCommandResult.invalid_arguments(
                command_id, "missing_tool_names"
            )
        unknown = [name for name in requested if name not in available_names]
        if unknown:
            return StandardSessionCommandResult.invalid_arguments(
                command_id,
                "unknown_tool",
                {"unknown": unknown, "available": available_names},
            )
        if action == "on":
            next_tools = [*active_tools, *(name for name in requested if name not in active_tools)]
        elif action == "off":
            next_tools = [name for name in active_tools if name not in set(requested)]
        else:
            next_tools = requested
        next_tools = _filter_available_tools(next_tools, available_names)
    await _resolve(ports.set_active_tools(next_tools))
    return StandardSessionCommandResult.completed(
        command_id,
        _tools_result(
            next_tools,
            _available_tool_entries(ports.get_all_tools(), next_tools),
            action=None if action == "reset" else action,
        ),
    )


def _tools_result(
    active_tools: list[str],
    available_tools: list[dict[str, object]],
    *,
    action: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "active_tools": active_tools,
        "available_tools": available_tools,
    }
    if action is not None:
        result["action"] = action
    return result


async def _execute_extensions_command(
    args: str, ports: StandardSessionCommandPorts
) -> StandardSessionCommandResult:
    command_id = StandardSessionCommandId.EXTENSIONS
    if ports.get_extensions is None:
        return StandardSessionCommandResult.unavailable(command_id)
    extensions = [_extension_entry(extension) for extension in ports.get_extensions()]
    query = args.strip()
    if not query:
        return StandardSessionCommandResult.completed(
            command_id, {"extensions": extensions, "query": None, "selected": None}
        )
    selected = next(
        (
            extension
            for extension in extensions
            if query
            in {
                _extension_field(extension, "id"),
                _extension_field(extension, "name"),
                _extension_field(extension, "runtimeName"),
            }
        ),
        None,
    )
    return StandardSessionCommandResult.completed(
        command_id,
        {"extensions": extensions, "query": query, "selected": selected},
    )


def _execute_copy_command(
    args: str, ports: StandardSessionCommandPorts
) -> StandardSessionCommandResult:
    command_id = StandardSessionCommandId.COPY
    index = _parse_copy_index(args)
    if index is None:
        return StandardSessionCommandResult.invalid_arguments(
            command_id, "invalid_copy_index"
        )
    if ports.get_recent_assistant_texts is None and ports.get_last_assistant_text is None:
        return StandardSessionCommandResult.unavailable(command_id)
    texts = (
        tuple(ports.get_recent_assistant_texts())
        if ports.get_recent_assistant_texts is not None
        else (
            (text,)
            if ports.get_last_assistant_text is not None
            and (text := ports.get_last_assistant_text())
            else ()
        )
    )
    if index > len(texts):
        return StandardSessionCommandResult.completed(
            command_id,
            {"copied": False, "characters": 0, "index": index, "available": True},
        )
    if ports.copy_text is None:
        return StandardSessionCommandResult.unavailable(command_id)
    text = texts[index - 1]
    result = ports.copy_text(text)
    return StandardSessionCommandResult.completed(
        command_id,
        {
            "copied": bool(getattr(result, "ok", False)),
            "characters": len(text),
            "index": index,
            "available": True,
            "command": getattr(result, "command", None),
            "message": getattr(result, "message", None),
        },
    )


def _parse_copy_index(args: str) -> int | None:
    stripped = args.strip()
    if not stripped:
        return 1
    tokens = _split_args(stripped)
    if len(tokens) != 1:
        return None
    try:
        value = int(tokens[0])
    except ValueError:
        return None
    return value if value > 0 else None


def _extension_entry(extension: object) -> dict[str, object]:
    if isinstance(extension, Mapping):
        return dict(extension)
    name = _object_field(extension, "name")
    return {
        "id": _object_field(extension, "id") or name,
        "name": name,
        "runtimeName": _object_field(extension, "runtimeName"),
    }


def _extension_field(extension: Mapping[str, object], field: str) -> str:
    value = extension.get(field)
    return value if isinstance(value, str) else ""


def _object_field(value: object, field: str) -> str:
    raw = getattr(value, field, None)
    return raw if isinstance(raw, str) else ""


def _available_tool_entries(
    tools: list[object], active_tools: list[str]
) -> list[dict[str, object]]:
    active_set = set(active_tools)
    entries: list[dict[str, object]] = []
    for tool in tools:
        name = _tool_field(tool, "name")
        if not name:
            continue
        entry: dict[str, object] = {
            "name": name,
            "active": name in active_set,
            "description": _tool_field(tool, "description"),
        }
        source_info = _tool_source_info(tool)
        if source_info is not None:
            entry["sourceInfo"] = dict(source_info)
        entries.append(entry)
    return entries


def _tool_field(tool: object, field: str) -> str:
    value = tool.get(field) if isinstance(tool, Mapping) else getattr(tool, field, None)
    return value if isinstance(value, str) else ""


def _tool_source_info(tool: object) -> Mapping[object, object] | None:
    value = (
        tool.get("sourceInfo") or tool.get("source_info")
        if isinstance(tool, Mapping)
        else getattr(tool, "sourceInfo", None) or getattr(tool, "source_info", None)
    )
    return value if isinstance(value, Mapping) else None


def _parse_tool_names(tokens: list[str]) -> list[str]:
    names: list[str] = []
    for token in tokens:
        for name in token.split(","):
            cleaned = name.strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
    return names


def _filter_available_tools(tool_names: list[str], available_names: list[str]) -> list[str]:
    available = set(available_names)
    return [name for name in tool_names if name in available]


def project_standard_session_command_result(
    result: StandardSessionCommandResult,
) -> dict[str, object]:
    """Project a standard result into the neutral command result mapping."""

    command = result.command_id.value
    if result.disposition == "unavailable":
        return _unsupported_command_result(command)
    if result.disposition == "invalid_arguments":
        return _error_command_result(command, _standard_argument_error(result))

    match result.command_id:
        case StandardSessionCommandId.SESSION:
            session = result.value
            if isinstance(session, Mapping):
                session = dict(session)
            return _ok_command_result(command, session=session)
        case StandardSessionCommandId.RENAME:
            name = result.value
            return _ok_command_result(
                command,
                name=name,
                message=(
                    f"Session renamed to {name}"
                    if isinstance(name, str)
                    else "Session name cleared"
                ),
            )
        case StandardSessionCommandId.EXPORT:
            export = result.value
            if not isinstance(export, StandardSessionExport):
                raise TypeError("standard export command returned an invalid result")
            return _ok_command_result(command, format=export.format, path=export.path)
        case StandardSessionCommandId.IMPORT | StandardSessionCommandId.COMPACT:
            return _ok_command_result(command, result=_to_plain_data(result.value))
        case StandardSessionCommandId.RELOAD:
            return _ok_command_result(command, reloaded=True)
        case StandardSessionCommandId.NEW:
            value = _to_plain_data(result.value)
            cancelled = isinstance(value, Mapping) and value.get("cancelled") is True
            return _ok_command_result(
                command,
                result=value,
                message=(
                    "New session creation cancelled."
                    if cancelled
                    else "Started a new session."
                ),
            )
        case (
            StandardSessionCommandId.RESUME
            | StandardSessionCommandId.FORK
            | StandardSessionCommandId.CLONE
            | StandardSessionCommandId.TREE
        ):
            return _ok_command_result(command, result=_to_plain_data(result.value))
        case StandardSessionCommandId.TOOLS:
            value = result.value
            if not isinstance(value, Mapping):
                raise TypeError("standard tools command returned an invalid result")
            active_tools = value.get("active_tools", [])
            available_tools = value.get("available_tools", [])
            if not isinstance(active_tools, list) or not isinstance(
                available_tools, list
            ):
                raise TypeError("standard tools command returned invalid tool data")
            fields: dict[str, object] = {
                "active_tools": [name for name in active_tools if isinstance(name, str)],
                "available_tools": [
                    entry for entry in available_tools if isinstance(entry, dict)
                ],
                "message": (
                    "Active tools: "
                    + ", ".join(name for name in active_tools if isinstance(name, str))
                    if active_tools
                    else "Active tools: (none)"
                ),
            }
            action = value.get("action")
            if isinstance(action, str):
                fields["action"] = action
            return _ok_command_result(command, **fields)
        case StandardSessionCommandId.EXTENSIONS:
            value = result.value
            if not isinstance(value, Mapping):
                raise TypeError(
                    "standard extensions command returned an invalid result"
                )
            extensions = value.get("extensions", [])
            query = value.get("query")
            selected = value.get("selected")
            if not isinstance(extensions, list):
                raise TypeError("standard extensions command returned invalid data")
            extensions = [entry for entry in extensions if isinstance(entry, dict)]
            if not isinstance(query, str) or not query:
                return _extensions_command_result(extensions)
            if not isinstance(selected, Mapping):
                available = ", ".join(
                    _extension_id(extension) for extension in extensions
                ) or "(none)"
                return _error_command_result(
                    command,
                    f"Unknown extension: {query}. Loaded extensions: {available}",
                )
            return _ok_command_result(
                command,
                extension=dict(selected),
                message=f"Extension {_extension_id(selected)}: "
                f"{_extension_name(selected)}",
                display=_extension_detail_display(selected),
            )
        case StandardSessionCommandId.COPY:
            value = result.value
            if not isinstance(value, Mapping):
                raise TypeError("standard copy command returned an invalid result")
            index = value.get("index", 1)
            if not isinstance(index, int):
                index = 1
            if not value.get("available", False):
                return _unsupported_command_result(command)
            if not value.get("copied", False):
                return _ok_command_result(
                    command,
                    copied=False,
                    characters=0,
                    message=f"No assistant text is available for /copy {index}.",
                    index=index,
                )
            return _ok_command_result(
                command,
                copied=True,
                characters=value.get("characters", 0),
                command_backend=value.get("command"),
                message=value.get("message"),
                index=index,
            )
        case StandardSessionCommandId.CHANGELOG:
            return _ok_command_result(command, changelog=_to_plain_data(result.value))


def _to_plain_data(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_data(item) for item in value]
    return value


def _standard_argument_error(result: StandardSessionCommandResult) -> str:
    match result.command_id, result.error_code:
        case StandardSessionCommandId.COPY, "invalid_copy_index":
            return "Usage: /copy [N], where N is a positive integer."
        case StandardSessionCommandId.TOOLS, "unknown_tool":
            value = result.value
            if isinstance(value, Mapping):
                unknown = value.get("unknown", [])
                available = value.get("available", [])
                if isinstance(unknown, list) and isinstance(available, list):
                    return (
                        f"Unknown tool: {', '.join(str(item) for item in unknown)}. "
                        f"Available tools: {', '.join(str(item) for item in available)}"
                    )
            return "Unknown tool"
        case StandardSessionCommandId.RESUME, "missing_reference":
            return "Usage: /resume <session-id-or-path>"
        case StandardSessionCommandId.NEW, "unexpected_arguments":
            return "Usage: /new"
        case StandardSessionCommandId.DELETE, "unexpected_arguments":
            return "Usage: /delete"
        case StandardSessionCommandId.FORK, "missing_record_id":
            return "Usage: /fork <entry-id> [before|at]"
        case StandardSessionCommandId.FORK, "invalid_fork_position":
            return f"Unsupported fork position: {result.value}"
        case StandardSessionCommandId.IMPORT, "missing_import_path":
            return "Usage: /import <jsonl-path> [cwd]"
        case StandardSessionCommandId.TREE, "missing_record_id":
            return "Usage: /tree <entry-id> [--summarize] [--label <label>]"
        case _:
            return f"Invalid arguments for /{result.command_id.value}"


def _ok_command_result(command: str, **fields: object) -> dict[str, object]:
    return {"source": "builtin", "command": command, "status": "ok", **fields}


def _error_command_result(command: str, message: str) -> dict[str, object]:
    return {
        "source": "builtin",
        "command": command,
        "status": "error",
        "message": message,
    }


def _unsupported_command_result(command: str) -> dict[str, object]:
    return {
        "source": "builtin",
        "command": command,
        "status": "unsupported",
        "message": f'Builtin command "/{command}" is handled by the interactive shell.',
    }


def _extensions_command_result(
    extensions: list[dict[str, object]],
) -> dict[str, object]:
    if not extensions:
        return _ok_command_result(
            "extensions",
            extensions=[],
            message="Extensions: (none)",
            display="Extensions:\n(none)",
        )
    summary = "; ".join(_extension_summary(extension) for extension in extensions)
    lines = ["Extensions:"]
    for extension in extensions:
        lines.append(
            f"- {_extension_id(extension)} - {_extension_name(extension)} "
            f"[{_string_mapping_field(extension, 'permissionLevel', default='safe')}]"
        )
        source_path = _string_mapping_field(extension, "sourcePath")
        if source_path:
            lines.append(f"  Source: {source_path}")
        surfaces = _surface_records(extension)
        if surfaces:
            lines.append(f"  Surfaces: {_surfaces_summary(surfaces)}")
        diagnostics = _list_field(extension, "diagnostics")
        if diagnostics:
            lines.append(f"  Diagnostics: {len(diagnostics)}")
    return _ok_command_result(
        "extensions",
        extensions=extensions,
        message=f"Extensions: {summary}",
        display="\n".join(lines),
    )


def _extension_summary(extension: Mapping[str, object]) -> str:
    surfaces = len(_surface_records(extension))
    diagnostics = len(_list_field(extension, "diagnostics"))
    details = [_string_mapping_field(extension, "permissionLevel", default="safe")]
    details.append(f"{surfaces} {'surface' if surfaces == 1 else 'surfaces'}")
    if diagnostics:
        details.append(f"{diagnostics} {'diagnostic' if diagnostics == 1 else 'diagnostics'}")
    return f"{_extension_id(extension)} ({', '.join(details)})"


def _extension_detail_display(extension: Mapping[str, object]) -> str:
    lines = [f"Extension {_extension_id(extension)}", f"Name: {_extension_name(extension)}"]
    for label, field in (("Version", "version"), ("Description", "description")):
        value = _string_mapping_field(extension, field)
        if value:
            lines.append(f"{label}: {value}")
    lines.append(
        f"Permission: {_string_mapping_field(extension, 'permissionLevel', default='safe')}"
    )
    capabilities = [
        item
        for item in _list_field(extension, "capabilities")
        if isinstance(item, str) and item
    ]
    lines.append(f"Capabilities: {', '.join(capabilities) if capabilities else '(none)'}")
    source_path = _string_mapping_field(extension, "sourcePath")
    if source_path:
        lines.append(f"Source: {source_path}")
    manifest_path = _string_mapping_field(extension, "manifestPath")
    if manifest_path:
        lines.append(f"Manifest: {manifest_path}")
    surfaces = _surface_records(extension)
    lines.append("Surfaces:")
    if surfaces:
        for surface in surfaces:
            if isinstance(surface, Mapping):
                surface_type = _string_mapping_field(surface, "type", default="surface")
                name = _string_mapping_field(surface, "name", default="(unnamed)")
                source = _string_mapping_field(surface, "source")
                lines.append(f"- {surface_type} {name}{f' ({source})' if source else ''}")
    else:
        lines.append("- (none)")
    diagnostics = _list_field(extension, "diagnostics")
    lines.append("Diagnostics:")
    if diagnostics:
        for diagnostic in diagnostics:
            if isinstance(diagnostic, Mapping):
                code = _string_mapping_field(diagnostic, "code", default="diagnostic")
                message = _string_mapping_field(diagnostic, "message")
                lines.append(f"- {code}: {message}" if message else f"- {code}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)


def _surface_records(extension: Mapping[str, object]) -> list[object]:
    surfaces = _list_field(extension, "surfaces")
    return surfaces if surfaces else _list_field(extension, "contributions")


def _surfaces_summary(surfaces: list[object]) -> str:
    parts = []
    for surface in surfaces:
        if isinstance(surface, Mapping):
            name = _string_mapping_field(surface, "name")
            if name:
                parts.append(
                    f"{_string_mapping_field(surface, 'type', default='surface')} {name}"
                )
    return ", ".join(parts) if parts else "(none)"


def _extension_id(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "id", default=_extension_name(extension))


def _extension_name(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "name", default="")


def _string_mapping_field(
    value: Mapping[str, object], field: str, *, default: str = ""
) -> str:
    raw = value.get(field)
    return raw if isinstance(raw, str) and raw else default


def _list_field(value: Mapping[str, object], field: str) -> list[object]:
    raw = value.get(field)
    return list(raw) if isinstance(raw, (list, tuple)) else []


__all__ = [
    "STANDARD_SESSION_COMMANDS",
    "STANDARD_SESSION_COMMAND_PROFILE",
    "StandardSessionCommandDisposition",
    "StandardSessionCommandDefinition",
    "StandardSessionExport",
    "StandardSessionCommandId",
    "StandardSessionCommandPorts",
    "StandardSessionCommandProfile",
    "StandardSessionCommandResult",
    "execute_standard_session_command_async",
    "is_standard_session_command",
    "list_standard_session_command_descriptors",
    "project_standard_session_command_result",
]
