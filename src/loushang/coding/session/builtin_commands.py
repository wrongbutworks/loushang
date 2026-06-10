from __future__ import annotations

import inspect
import shlex
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path

from loushang.coding.commands.types import (
    BUILTIN_SLASH_COMMANDS,
    SessionCommandDescriptor,
)
from loushang.coding.platform.changelog import (
    find_changelog_path,
    format_changelog_entries,
    parse_changelog,
)
from loushang.coding.platform.clipboard import ClipboardCopyResult, copy_to_clipboard
from loushang.coding.session.types import CommandExecutionResult
from loushang.coding.source_info import create_source_info

BuiltinCallable = Callable[..., object | Awaitable[object]]


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
    copy_text: Callable[[str], ClipboardCopyResult] = copy_to_clipboard
    get_changelog: Callable[[str], object] | None = None
    new_session: Callable[[object | None], object | Awaitable[object]] | None = None
    resume_session: Callable[[str, object | None], object | Awaitable[object]] | None = None
    fork_session: Callable[[str, object | None], object | Awaitable[object]] | None = None
    clone_session: Callable[[], object | Awaitable[object]] | None = None
    navigate_tree: Callable[[str, object | None], object | Awaitable[object]] | None = None
    import_session: Callable[[str, str | None], object | Awaitable[object]] | None = None
    get_active_tool_names: Callable[[], list[str]] | None = None
    get_all_tools: Callable[[], list[object]] | None = None
    set_active_tools: Callable[[list[str]], object | Awaitable[object]] | None = None
    get_default_active_tool_names: Callable[[], list[str]] | None = None
    get_extensions: Callable[[], list[object]] | None = None


def list_builtin_command_descriptors() -> list[SessionCommandDescriptor]:
    source_info = create_source_info("<builtin>", source="builtin", scope="project", origin="package")
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
    invocation_name = invocation_name[1:] if invocation_name.startswith("/") else invocation_name
    if invocation_name not in _BUILTIN_COMMAND_NAMES:
        return None

    match invocation_name:
        case "name":
            return await _execute_name(args, backend)
        case "session":
            return _execute_session(backend)
        case "export":
            return _execute_export(args, backend)
        case "copy":
            return _execute_copy(args, backend)
        case "changelog":
            return _execute_changelog(args, backend)
        case "tools":
            return await _execute_tools(args, backend)
        case "extensions":
            return _execute_extensions(args, backend)
        case "compact":
            return await _execute_compact(args, backend)
        case "reload":
            return await _execute_reload(backend)
        case "new":
            return await _execute_new(args, backend)
        case "resume":
            return await _execute_resume(args, backend)
        case "fork":
            return await _execute_fork(args, backend)
        case "clone":
            return await _execute_clone(backend)
        case "tree":
            return await _execute_tree(args, backend)
        case "import":
            return await _execute_import(args, backend)
        case _:
            return _unsupported(invocation_name)


async def _execute_name(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.set_session_name is None:
        return _unsupported("name")
    name = args.strip() or None
    await _maybe_await(backend.set_session_name(name))
    return _ok("name", name=name)


def _execute_session(backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.get_session_info is None:
        return _unsupported("session")
    return _ok("session", session=dict(backend.get_session_info()))


def _execute_export(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    raw_path = args.strip() or None
    wants_jsonl = raw_path is not None and raw_path.lower().endswith(".jsonl")
    export_fn = backend.export_to_jsonl if wants_jsonl else backend.export_to_html
    export_format = "jsonl" if wants_jsonl else "html"
    if export_fn is None:
        return _unsupported("export")
    path = export_fn(raw_path)
    return _ok("export", format=export_format, path=path)


def _execute_copy(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    copy_index = _parse_copy_index(args)
    if copy_index is None:
        return _error("copy", "Usage: /copy [N], where N is a positive integer.")
    texts = _recent_assistant_texts(backend)
    if not texts:
        if backend.get_recent_assistant_texts is None and backend.get_last_assistant_text is None:
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


def _execute_changelog(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.get_changelog is None:
        return _unsupported("changelog")
    return _ok("changelog", changelog=_to_plain_data(backend.get_changelog(args)))


async def _execute_tools(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.get_active_tool_names is None or backend.get_all_tools is None:
        return _unsupported("tools")
    active_tools = list(backend.get_active_tool_names())
    available_tools = _available_tool_entries(backend.get_all_tools(), active_tools)
    available_names = [entry["name"] for entry in available_tools]
    tokens = _split_args(args.strip()) if args.strip() else []
    if not tokens:
        return _tools_ok(active_tools, available_tools)

    action = tokens[0]
    if action == "reset":
        if len(tokens) != 1:
            return _error("tools", "Usage: /tools reset")
        if backend.get_default_active_tool_names is None or backend.set_active_tools is None:
            return _unsupported("tools")
        next_tools = _filter_available_tools(backend.get_default_active_tool_names(), available_names)
        await _maybe_await(backend.set_active_tools(next_tools))
        return _tools_ok(next_tools, _available_tool_entries(backend.get_all_tools(), next_tools), action="reset")

    if action not in {"on", "off", "only"}:
        return _error("tools", "Usage: /tools [on|off|only <tool[,tool]...>|reset]")
    if backend.set_active_tools is None:
        return _unsupported("tools")
    requested = _parse_tool_names(tokens[1:])
    if not requested:
        return _error("tools", f"Usage: /tools {action} <tool[,tool]...>")
    unknown = [name for name in requested if name not in available_names]
    if unknown:
        return _error("tools", f"Unknown tool: {', '.join(unknown)}. Available tools: {', '.join(available_names)}")

    if action == "on":
        next_tools = [*active_tools, *(name for name in requested if name not in active_tools)]
    elif action == "off":
        remove = set(requested)
        next_tools = [name for name in active_tools if name not in remove]
    else:
        next_tools = requested
    next_tools = _filter_available_tools(next_tools, available_names)
    await _maybe_await(backend.set_active_tools(next_tools))
    return _tools_ok(next_tools, _available_tool_entries(backend.get_all_tools(), next_tools), action=action)


def _execute_extensions(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.get_extensions is None:
        return _unsupported("extensions")
    extensions = [_extension_entry(extension) for extension in backend.get_extensions()]
    query = args.strip()
    if not query:
        return _extensions_ok(extensions)

    extension = _find_extension(extensions, query)
    if extension is None:
        available = ", ".join(_extension_id(extension) for extension in extensions) or "(none)"
        return _error("extensions", f"Unknown extension: {query}. Loaded extensions: {available}")
    return _ok(
        "extensions",
        extension=extension,
        message=f"Extension {_extension_id(extension)}: {_extension_name(extension)}",
        display=_extension_detail_display(extension),
    )


async def _execute_compact(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.compact is None:
        return _unsupported("compact")
    result = await _maybe_await(backend.compact(args.strip() or None))
    return _ok("compact", result=_to_plain_data(result))


async def _execute_reload(backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.reload is None:
        return _unsupported("reload")
    await _maybe_await(backend.reload())
    return _ok("reload", reloaded=True)


async def _execute_new(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.new_session is None:
        return _unsupported("new")
    tokens = _split_args(args)
    options: dict[str, object] = {}
    if tokens:
        options["cwd"] = tokens[0]
    result = await _maybe_await(backend.new_session(options or None))
    return _ok("new", result=_to_plain_data(result))


async def _execute_resume(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.resume_session is None:
        return _unsupported("resume")
    tokens = _split_args(args)
    if not tokens:
        return _error("resume", "Usage: /resume <session-id-or-path>")
    result = await _maybe_await(backend.resume_session(tokens[0], None))
    return _ok("resume", result=_to_plain_data(result))


async def _execute_fork(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.fork_session is None:
        return _unsupported("fork")
    tokens = _split_args(args)
    if not tokens:
        return _error("fork", "Usage: /fork <entry-id> [before|at]")
    options: dict[str, object] = {}
    if len(tokens) > 1:
        if tokens[1] not in {"before", "at"}:
            return _error("fork", f"Unsupported fork position: {tokens[1]}")
        options["position"] = tokens[1]
    result = await _maybe_await(backend.fork_session(tokens[0], options or None))
    return _ok("fork", result=_to_plain_data(result))


async def _execute_clone(backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.clone_session is None:
        return _unsupported("clone")
    result = await _maybe_await(backend.clone_session())
    return _ok("clone", result=_to_plain_data(result))


async def _execute_tree(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.navigate_tree is None:
        return _unsupported("tree")
    tokens = _split_args(args)
    if not tokens:
        return _error("tree", "Usage: /tree <entry-id> [--summarize] [--label <label>]")
    target_id = tokens[0]
    options = _parse_tree_options(tokens[1:])
    result = await _maybe_await(backend.navigate_tree(target_id, options or None))
    return _ok("tree", result=_to_plain_data(result))


async def _execute_import(args: str, backend: BuiltinCommandBackend) -> CommandExecutionResult:
    if backend.import_session is None:
        return _unsupported("import")
    tokens = _split_args(args)
    if not tokens:
        return _error("import", "Usage: /import <jsonl-path> [cwd]")
    result = await _maybe_await(backend.import_session(tokens[0], tokens[1] if len(tokens) > 1 else None))
    return _ok("import", result=_to_plain_data(result))


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


def _tools_ok(active_tools: list[str], available_tools: list[dict[str, object]], *, action: str | None = None) -> CommandExecutionResult:
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


def _parse_tool_names(tokens: list[str]) -> list[str]:
    names: list[str] = []
    for token in tokens:
        for name in token.split(","):
            cleaned = name.strip()
            if cleaned and cleaned not in names:
                names.append(cleaned)
    return names


def _available_tool_entries(tools: list[object], active_tools: list[str]) -> list[dict[str, object]]:
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
    if isinstance(tool, Mapping):
        value = tool.get(field)
    else:
        value = getattr(tool, field, None)
    return value if isinstance(value, str) else ""


def _tool_source_info(tool: object) -> object | None:
    if isinstance(tool, Mapping):
        value = tool.get("sourceInfo") or tool.get("source_info")
    else:
        value = getattr(tool, "sourceInfo", None) or getattr(tool, "source_info", None)
    return value if isinstance(value, Mapping) else None


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
    contribution_count = len(_list_field(extension, "contributions"))
    diagnostic_count = len(_list_field(extension, "diagnostics"))
    details = [_string_mapping_field(extension, "permissionLevel", default="safe")]
    details.append(f"{contribution_count} {_pluralize('contribution', contribution_count)}")
    if diagnostic_count:
        details.append(f"{diagnostic_count} {_pluralize('diagnostic', diagnostic_count)}")
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
    contributions = _list_field(extension, "contributions")
    if contributions:
        lines.append(f"  Contributions: {_contributions_summary(contributions)}")
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
    lines.append(f"Permission: {_string_mapping_field(extension, 'permissionLevel', default='safe')}")
    lines.append(f"Capabilities: {_capabilities_text(extension)}")
    source_path = _string_mapping_field(extension, "sourcePath")
    if source_path:
        lines.append(f"Source: {source_path}")
    manifest_path = _string_mapping_field(extension, "manifestPath")
    if manifest_path:
        lines.append(f"Manifest: {manifest_path}")
    lines.extend(_contributions_detail_lines(_list_field(extension, "contributions")))
    lines.extend(_diagnostic_detail_lines(_list_field(extension, "diagnostics")))
    return "\n".join(lines)


def _contributions_summary(contributions: list[object]) -> str:
    parts: list[str] = []
    for contribution in contributions:
        if not isinstance(contribution, Mapping):
            continue
        contribution_type = _string_mapping_field(contribution, "type", default="contribution")
        name = _string_mapping_field(contribution, "name")
        if name:
            parts.append(f"{contribution_type} {name}")
    return ", ".join(parts) if parts else "(none)"


def _contributions_detail_lines(contributions: list[object]) -> list[str]:
    if not contributions:
        return ["Contributions:", "- (none)"]
    lines = ["Contributions:"]
    for contribution in contributions:
        if not isinstance(contribution, Mapping):
            continue
        contribution_type = _string_mapping_field(contribution, "type", default="contribution")
        name = _string_mapping_field(contribution, "name", default="(unnamed)")
        source = _string_mapping_field(contribution, "source")
        suffix = f" ({source})" if source else ""
        lines.append(f"- {contribution_type} {name}{suffix}")
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


def _find_extension(extensions: list[dict[str, object]], query: str) -> dict[str, object] | None:
    for extension in extensions:
        if query in {_extension_id(extension), _extension_name(extension), _runtime_name(extension)}:
            return extension
    return None


def _extension_entry(extension: object) -> dict[str, object]:
    if isinstance(extension, Mapping):
        return dict(extension)
    return {
        "id": _string_object_field(extension, "id", default=_string_object_field(extension, "name")),
        "name": _string_object_field(extension, "name"),
    }


def _extension_id(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "id", default=_extension_name(extension))


def _extension_name(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "name", default=_runtime_name(extension))


def _runtime_name(extension: Mapping[str, object]) -> str:
    return _string_mapping_field(extension, "runtimeName")


def _string_mapping_field(value: Mapping[str, object], field: str, *, default: str = "") -> str:
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


def _filter_available_tools(tool_names: list[str], available_names: list[str]) -> list[str]:
    available = set(available_names)
    return [name for name in tool_names if name in available]


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
        elif token in {"--instructions", "--custom-instructions"} and index + 1 < len(tokens):
            index += 1
            options["custom_instructions"] = tokens[index]
        index += 1
    return options


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
