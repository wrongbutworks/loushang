from __future__ import annotations

import inspect
import shlex
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Protocol

from loushang.coding.commands.types import BUILTIN_SLASH_COMMANDS
from loushang.coding.platform.changelog import (
    find_changelog_path,
    format_changelog_entries,
    parse_changelog,
)
from loushang.coding.session.types import CommandExecutionResult
from loushang.harness.commands import SessionCommandDescriptor
from loushang.harness.resources.source import create_source_info
from loushang.harness.session.command_pack import (
    StandardSessionCommandId,
    StandardSessionCommandPorts,
    StandardSessionCommandResult,
    StandardSessionExport,
    execute_standard_session_command_async,
)

BuiltinCallable = Callable[..., object | Awaitable[object]]


class ClipboardCopyResultPort(Protocol):
    @property
    def ok(self) -> bool: ...

    @property
    def command(self) -> str | None: ...

    @property
    def message(self) -> str | None: ...


def _copy_to_clipboard(text: str) -> ClipboardCopyResultPort:
    from loushang.tui.clipboard import copy_to_clipboard

    return copy_to_clipboard(text)


@dataclass
class BuiltinCommandBackend:
    get_session_info: Callable[[], Mapping[str, object]] | None = None
    set_session_name: Callable[[str | None], object] | None = None
    export_to_html: Callable[[str | None], str] | None = None
    export_to_jsonl: Callable[[str | None], str] | None = None
    compact: Callable[[str | None], object | Awaitable[object]] | None = None
    reload: Callable[[], object | Awaitable[object]] | None = None
    get_recent_assistant_texts: Callable[[], tuple[str, ...]] | None = None
    get_last_assistant_text: Callable[[], str | None] | None = None
    copy_text: Callable[[str], ClipboardCopyResultPort] = _copy_to_clipboard
    get_changelog: Callable[[str], object] | None = None
    new_session: Callable[[object | None], object | Awaitable[object]] | None = None
    resume_session: (
        Callable[[str, object | None], object | Awaitable[object]] | None
    ) = None
    fork_session: Callable[[str, object | None], object | Awaitable[object]] | None = (
        None
    )
    clone_session: Callable[[], object | Awaitable[object]] | None = None
    navigate_tree: Callable[[str, object | None], object | Awaitable[object]] | None = (
        None
    )
    import_session: Callable[[str, str | None], object | Awaitable[object]] | None = (
        None
    )
    get_active_tool_names: Callable[[], list[str]] | None = None
    get_all_tools: Callable[[], list[object]] | None = None
    set_active_tools: Callable[[list[str]], object | Awaitable[object]] | None = None
    get_default_active_tool_names: Callable[[], list[str]] | None = None
    get_extensions: Callable[[], list[object]] | None = None


def list_builtin_command_descriptors() -> list[SessionCommandDescriptor]:
    source_info = create_source_info(
        "<builtin>", source="builtin", scope="project", origin="package"
    )
    return [
        SessionCommandDescriptor(
            name=command.name,
            description=command.description,
            source="builtin",
            source_info=source_info,
        )
        for command in BUILTIN_SLASH_COMMANDS
    ]


def is_builtin_command(invocation_name: str) -> bool:
    return invocation_name in _BUILTIN_COMMAND_NAMES


async def execute_builtin_command_async(
    invocation_name: str,
    args: str,
    backend: BuiltinCommandBackend,
) -> CommandExecutionResult | None:
    invocation_name = (
        invocation_name[1:] if invocation_name.startswith("/") else invocation_name
    )
    if invocation_name not in _BUILTIN_COMMAND_NAMES:
        return None

    standard_result = await execute_standard_session_command_async(
        invocation_name,
        args,
        _standard_session_command_ports(backend),
    )
    if standard_result is not None:
        return _project_standard_session_command_result(standard_result)

    match invocation_name:
        case "copy":
            return _execute_copy(args, backend)
        case "changelog":
            return _execute_changelog(args, backend)
        case "extensions":
            return _execute_extensions(args, backend)
        case _:
            return _unsupported(invocation_name)


def _standard_session_command_ports(
    backend: BuiltinCommandBackend,
) -> StandardSessionCommandPorts:
    return StandardSessionCommandPorts(
        get_session_info=backend.get_session_info,
        set_session_name=backend.set_session_name,
        export_html=backend.export_to_html,
        export_jsonl=backend.export_to_jsonl,
        import_session=backend.import_session,
        compact=backend.compact,
        reload=backend.reload,
        new_session=backend.new_session,
        resume_session=backend.resume_session,
        fork_session=backend.fork_session,
        clone_session=backend.clone_session,
        navigate_tree=backend.navigate_tree,
        get_active_tool_names=backend.get_active_tool_names,
        get_all_tools=backend.get_all_tools,
        set_active_tools=backend.set_active_tools,
        get_default_active_tool_names=backend.get_default_active_tool_names,
    )


def _project_standard_session_command_result(
    result: StandardSessionCommandResult,
) -> CommandExecutionResult:
    command = result.command_id.value
    if result.disposition == "unavailable":
        return _unsupported(command)
    if result.disposition == "invalid_arguments":
        return _error(command, _standard_argument_error(result))

    match result.command_id:
        case StandardSessionCommandId.SESSION:
            session = result.value
            if isinstance(session, Mapping):
                session = dict(session)
            return _ok(command, session=session)
        case StandardSessionCommandId.NAME:
            return _ok(command, name=result.value)
        case StandardSessionCommandId.EXPORT:
            export = result.value
            if not isinstance(export, StandardSessionExport):
                raise TypeError("standard export command returned an invalid result")
            return _ok(command, format=export.format, path=export.path)
        case StandardSessionCommandId.IMPORT:
            return _ok(command, result=_to_plain_data(result.value))
        case StandardSessionCommandId.COMPACT:
            return _ok(command, result=_to_plain_data(result.value))
        case StandardSessionCommandId.RELOAD:
            return _ok(command, reloaded=True)
        case (
            StandardSessionCommandId.NEW
            | StandardSessionCommandId.RESUME
            | StandardSessionCommandId.FORK
            | StandardSessionCommandId.CLONE
            | StandardSessionCommandId.TREE
        ):
            return _ok(command, result=_to_plain_data(result.value))
        case StandardSessionCommandId.TOOLS:
            value = result.value
            if not isinstance(value, Mapping):
                raise TypeError("standard tools command returned an invalid result")
            active_tools = value.get("active_tools", [])
            available_tools = value.get("available_tools", [])
            if not isinstance(active_tools, list) or not isinstance(available_tools, list):
                raise TypeError("standard tools command returned invalid tool data")
            return _tools_ok(
                [name for name in active_tools if isinstance(name, str)],
                [entry for entry in available_tools if isinstance(entry, dict)],
                action=value.get("action") if isinstance(value.get("action"), str) else None,
            )


def _standard_argument_error(result: StandardSessionCommandResult) -> str:
    match result.command_id, result.error_code:
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


def _execute_copy(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    copy_index = _parse_copy_index(args)
    if copy_index is None:
        return _error("copy", "Usage: /copy [N], where N is a positive integer.")
    texts = _recent_assistant_texts(backend)
    if not texts:
        if (
            backend.get_recent_assistant_texts is None
            and backend.get_last_assistant_text is None
        ):
            return _unsupported("copy")
        return _ok(
            "copy",
            copied=False,
            characters=0,
            message=f"No assistant text is available for /copy {copy_index}.",
            index=copy_index,
        )
    text_index = copy_index - 1
    if text_index >= len(texts):
        return _ok(
            "copy",
            copied=False,
            characters=0,
            message=f"No assistant text is available for /copy {copy_index}.",
            index=copy_index,
        )
    text = texts[text_index]
    result = backend.copy_text(text)
    return _ok(
        "copy",
        copied=result.ok,
        characters=len(text),
        command_backend=result.command,
        message=result.message,
        index=copy_index,
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


def _recent_assistant_texts(backend: BuiltinCommandBackend) -> tuple[str, ...]:
    if backend.get_recent_assistant_texts is not None:
        return tuple(backend.get_recent_assistant_texts())
    if backend.get_last_assistant_text is None:
        return ()
    text = backend.get_last_assistant_text()
    if not text:
        return ()
    return (text,)


def _execute_changelog(
    args: str, backend: BuiltinCommandBackend
) -> CommandExecutionResult:
    if backend.get_changelog is None:
        return _unsupported("changelog")
    return _ok("changelog", changelog=_to_plain_data(backend.get_changelog(args)))


def _execute_extensions(
    args: str, backend: BuiltinCommandBackend
) -> CommandExecutionResult:
    if backend.get_extensions is None:
        return _unsupported("extensions")
    extensions = [_extension_entry(extension) for extension in backend.get_extensions()]
    query = args.strip()
    if not query:
        return _extensions_ok(extensions)

    extension = _find_extension(extensions, query)
    if extension is None:
        available = (
            ", ".join(_extension_id(extension) for extension in extensions) or "(none)"
        )
        return _error(
            "extensions", f"Unknown extension: {query}. Loaded extensions: {available}"
        )
    return _ok(
        "extensions",
        extension=extension,
        message=f"Extension {_extension_id(extension)}: {_extension_name(extension)}",
        display=_extension_detail_display(extension),
    )


def read_changelog_for_cwd(cwd: str | Path, args: str = "") -> dict[str, object]:
    del args
    path = find_changelog_path(cwd)
    if path is None:
        return {"path": None, "entries": [], "text": ""}
    entries = parse_changelog(path)
    text = format_changelog_entries(entries, limit=3)
    return {
        "path": path.as_posix(),
        "entries": [_to_plain_data(entry) for entry in entries[:3]],
        "text": text,
    }


def _ok(command: str, **fields: object) -> CommandExecutionResult:
    return CommandExecutionResult(
        invocation_name=command,
        result={
            "source": "builtin",
            "command": command,
            "status": "ok",
            **fields,
        },
    )


def _error(command: str, message: str) -> CommandExecutionResult:
    return CommandExecutionResult(
        invocation_name=command,
        result={
            "source": "builtin",
            "command": command,
            "status": "error",
            "message": message,
        },
    )


def _unsupported(command: str) -> CommandExecutionResult:
    return CommandExecutionResult(
        invocation_name=command,
        result={
            "source": "builtin",
            "command": command,
            "status": "unsupported",
            "message": f'Builtin command "/{command}" is handled by the interactive shell.',
        },
    )


def _tools_ok(
    active_tools: list[str],
    available_tools: list[dict[str, object]],
    *,
    action: str | None = None,
) -> CommandExecutionResult:
    fields: dict[str, object] = {
        "active_tools": active_tools,
        "available_tools": available_tools,
        "message": f"Active tools: {', '.join(active_tools) if active_tools else '(none)'}",
    }
    if action is not None:
        fields["action"] = action
    return _ok("tools", **fields)


async def _maybe_await(value: object | Awaitable[object]) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _split_args(args: str) -> list[str]:
    try:
        return shlex.split(args)
    except ValueError:
        return args.split()


def _extensions_ok(extensions: list[dict[str, object]]) -> CommandExecutionResult:
    return _ok(
        "extensions",
        extensions=extensions,
        message=_extensions_summary_message(extensions),
        display=_extensions_display(extensions),
    )


def _extensions_summary_message(extensions: list[dict[str, object]]) -> str:
    if not extensions:
        return "Extensions: (none)"
    parts = [_extension_summary(extension) for extension in extensions]
    return f"Extensions: {'; '.join(parts)}"


def _extension_summary(extension: Mapping[str, object]) -> str:
    surface_count = len(_surface_records(extension))
    diagnostic_count = len(_list_field(extension, "diagnostics"))
    details = [_string_mapping_field(extension, "permissionLevel", default="safe")]
    details.append(f"{surface_count} {_pluralize('surface', surface_count)}")
    if diagnostic_count:
        details.append(
            f"{diagnostic_count} {_pluralize('diagnostic', diagnostic_count)}"
        )
    return f"{_extension_id(extension)} ({', '.join(details)})"


def _extensions_display(extensions: list[dict[str, object]]) -> str:
    if not extensions:
        return "Extensions:\n(none)"
    lines = ["Extensions:"]
    for extension in extensions:
        lines.extend(_extension_list_display_lines(extension))
    return "\n".join(lines)


def _extension_list_display_lines(extension: Mapping[str, object]) -> list[str]:
    lines = [
        f"- {_extension_id(extension)} - {_extension_name(extension)} [{_string_mapping_field(extension, 'permissionLevel', default='safe')}]"
    ]
    source_path = _string_mapping_field(extension, "sourcePath")
    if source_path:
        lines.append(f"  Source: {source_path}")
    surfaces = _surface_records(extension)
    if surfaces:
        lines.append(f"  Surfaces: {_surfaces_summary(surfaces)}")
    diagnostics = _list_field(extension, "diagnostics")
    if diagnostics:
        lines.append(f"  Diagnostics: {len(diagnostics)}")
    return lines


def _extension_detail_display(extension: Mapping[str, object]) -> str:
    lines = [
        f"Extension {_extension_id(extension)}",
        f"Name: {_extension_name(extension)}",
    ]
    for label, field in (
        ("Version", "version"),
        ("Description", "description"),
    ):
        value = _string_mapping_field(extension, field)
        if value:
            lines.append(f"{label}: {value}")
    lines.append(
        f"Permission: {_string_mapping_field(extension, 'permissionLevel', default='safe')}"
    )
    lines.append(f"Capabilities: {_capabilities_text(extension)}")
    source_path = _string_mapping_field(extension, "sourcePath")
    if source_path:
        lines.append(f"Source: {source_path}")
    manifest_path = _string_mapping_field(extension, "manifestPath")
    if manifest_path:
        lines.append(f"Manifest: {manifest_path}")
    lines.extend(_surfaces_detail_lines(_surface_records(extension)))
    lines.extend(_diagnostic_detail_lines(_list_field(extension, "diagnostics")))
    return "\n".join(lines)


def _surface_records(extension: Mapping[str, object]) -> list[object]:
    surfaces = _list_field(extension, "surfaces")
    if surfaces:
        return surfaces
    return _list_field(extension, "contributions")


def _surfaces_summary(surfaces: list[object]) -> str:
    parts: list[str] = []
    for surface in surfaces:
        if not isinstance(surface, Mapping):
            continue
        surface_type = _string_mapping_field(surface, "type", default="surface")
        name = _string_mapping_field(surface, "name")
        if name:
            parts.append(f"{surface_type} {name}")
    return ", ".join(parts) if parts else "(none)"


def _surfaces_detail_lines(surfaces: list[object]) -> list[str]:
    if not surfaces:
        return ["Surfaces:", "- (none)"]
    lines = ["Surfaces:"]
    for surface in surfaces:
        if not isinstance(surface, Mapping):
            continue
        surface_type = _string_mapping_field(surface, "type", default="surface")
        name = _string_mapping_field(surface, "name", default="(unnamed)")
        source = _string_mapping_field(surface, "source")
        suffix = f" ({source})" if source else ""
        lines.append(f"- {surface_type} {name}{suffix}")
    return lines


def _diagnostic_detail_lines(diagnostics: list[object]) -> list[str]:
    if not diagnostics:
        return ["Diagnostics:", "- (none)"]
    lines = ["Diagnostics:"]
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, Mapping):
            continue
        code = _string_mapping_field(diagnostic, "code", default="diagnostic")
        message = _string_mapping_field(diagnostic, "message")
        if message:
            lines.append(f"- {code}: {message}")
        else:
            lines.append(f"- {code}")
    return lines


def _capabilities_text(extension: Mapping[str, object]) -> str:
    capabilities = [
        item
        for item in _list_field(extension, "capabilities")
        if isinstance(item, str) and item
    ]
    return ", ".join(capabilities) if capabilities else "(none)"


def _find_extension(
    extensions: list[dict[str, object]], query: str
) -> dict[str, object] | None:
    for extension in extensions:
        if query in {
            _extension_id(extension),
            _extension_name(extension),
            _runtime_name(extension),
        }:
            return extension
    return None


def _extension_entry(extension: object) -> dict[str, object]:
    if isinstance(extension, Mapping):
        return dict(extension)
    return {
        "id": _string_object_field(
            extension, "id", default=_string_object_field(extension, "name")
        ),
        "name": _string_object_field(extension, "name"),
    }


def _extension_id(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "id", default=_extension_name(extension))


def _extension_name(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "name", default=_runtime_name(extension))


def _runtime_name(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "runtimeName")


def _string_mapping_field(
    value: Mapping[str, object], field: str, *, default: str = ""
) -> str:
    raw = value.get(field)
    return raw if isinstance(raw, str) and raw else default


def _string_object_field(value: object, field: str, *, default: str = "") -> str:
    raw = getattr(value, field, None)
    return raw if isinstance(raw, str) and raw else default


def _list_field(value: Mapping[str, object], field: str) -> list[object]:
    raw = value.get(field)
    return list(raw) if isinstance(raw, list | tuple) else []


def _pluralize(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"


def _to_plain_data(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_plain_data(item) for item in value]
    return value


_BUILTIN_COMMAND_NAMES = frozenset(command.name for command in BUILTIN_SLASH_COMMANDS)


__all__ = [
    "BuiltinCommandBackend",
    "execute_builtin_command_async",
    "is_builtin_command",
    "list_builtin_command_descriptors",
    "read_changelog_for_cwd",
]
