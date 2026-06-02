from __future__ import annotations

from argparse import ArgumentParser, RawTextHelpFormatter
from dataclasses import dataclass
from typing import Literal, Mapping, TypeAlias

from loushang.coding.extensions.types import RegisteredFlag, ResolvedFlag

CliMode = Literal["text", "print", "json", "rpc"]
CommandListFormat = Literal["tsv", "json"]
DiagnosticListFormat = Literal["tsv", "json"]
ModelListFormat = Literal["text", "json"]
SessionListFormat = Literal["tsv", "json"]
SkillListFormat = Literal["tsv", "json"]
MethodListFormat = Literal["tsv", "json"]
MethodShowFormat = Literal["text", "json"]
PluginListFormat = Literal["tsv", "json"]
PackageListFormat = Literal["text", "tsv", "json"]
ExportFormat = Literal["html", "jsonl"]
ExportResultFormat = Literal["text", "json"]
CommandResultFormat = Literal["raw", "json"]
WorkLogInspectFormat = Literal["text", "json"]
ExtensionFlag: TypeAlias = RegisteredFlag | ResolvedFlag
_BUILTIN_FLAG_NAMES = frozenset(
    {
        "help",
        "version",
        "mode",
        "method",
        "prompt",
        "prompt-steps",
        "tui",
        "no-tui",
        "no-session",
        "session",
        "session-name",
        "list-sessions",
        "all-sessions",
        "list-sessions-format",
        "session-index",
        "refresh-session-index",
        "session-cwd",
        "session-name-filter",
        "session-parent",
        "session-query",
        "session-has-diagnostics",
        "session-no-diagnostics",
        "session-limit",
        "fork",
        "session-dir",
        "cwd",
        "provider",
        "model",
        "continue",
        "resume",
        "list-models",
        "list-models-format",
        "models",
        "extension",
        "no-extensions",
        "skill",
        "no-skills",
        "prompt-template",
        "no-prompt-templates",
        "theme",
        "no-themes",
        "api-key",
        "system-prompt",
        "append-system-prompt",
        "offline",
        "verbose",
        "debug",
        "debug-file",
        "trace",
        "trace-file",
        "export",
        "export-format",
        "export-result-format",
        "tool",
        "tools",
        "no-tools",
        "no-builtin-tools",
        "thinking",
        "no-context-files",
        "list-commands",
        "list-commands-format",
        "list-diagnostics",
        "list-diagnostics-format",
        "diagnostics-limit",
        "diag-export",
        "diag-output",
        "list-skills",
        "list-skills-format",
        "list-methods",
        "list-methods-format",
        "show-method",
        "show-method-format",
        "enable-skill",
        "disable-skill",
        "list-plugins",
        "list-plugins-format",
        "list-packages",
        "list-packages-format",
        "package-catalog",
        "install-package",
        "uninstall-package",
        "package-scope",
        "update-packages",
        "check-package-updates",
        "materialize-package",
        "update-package",
        "remove-package",
        "add-plugin-source",
        "remove-plugin-source",
        "enable-plugin",
        "disable-plugin",
        "command",
        "command-args",
        "command-result-format",
        "render-tool-events",
        "work-log",
        "work-log-inspect",
        "work-log-run",
        "work-log-inspect-format",
        "message",
    }
)


@dataclass(frozen=True)
class CliArgs:
    help: bool
    version: bool
    mode: CliMode
    method: str | None
    prompt: str | None
    prompt_steps: str | None
    tui: bool
    no_tui: bool
    continue_: bool
    resume: bool | str
    no_session: bool
    session: str | None
    session_name: str | None
    list_sessions: bool
    all_sessions: bool
    list_sessions_format: SessionListFormat
    session_index: bool
    refresh_session_index: bool
    session_cwd: str | None
    session_name_filter: str | None
    session_parent: str | None
    session_query: str | None
    session_has_diagnostics: bool | None
    session_limit: int | None
    fork: str | None
    session_dir: str | None
    cwd: str | None
    provider: str | None
    model: str | None
    thinking: str | None
    tools: tuple[str, ...]
    no_tools: bool
    no_builtin_tools: bool
    no_context_files: bool
    list_commands: bool
    list_commands_format: CommandListFormat
    list_diagnostics: bool
    list_diagnostics_format: DiagnosticListFormat
    diagnostics_limit: int
    diag_export: bool
    diag_output: str | None
    list_skills: bool
    list_skills_format: SkillListFormat
    list_methods: bool
    list_methods_format: MethodListFormat
    show_method: str | None
    show_method_format: MethodShowFormat
    enable_skills: tuple[str, ...]
    disable_skills: tuple[str, ...]
    list_plugins: bool
    list_plugins_format: PluginListFormat
    list_packages: bool
    list_packages_format: PackageListFormat
    package_catalog: str | None
    install_packages: tuple[str, ...]
    uninstall_packages: tuple[str, ...]
    package_scope: str
    update_all_packages: bool
    check_package_updates: bool
    materialize_packages: tuple[str, ...]
    update_packages: tuple[str, ...]
    remove_packages: tuple[str, ...]
    add_plugin_sources: tuple[str, ...]
    remove_plugin_sources: tuple[str, ...]
    enable_plugins: tuple[str, ...]
    disable_plugins: tuple[str, ...]
    command: str | None
    command_args: str
    command_result_format: CommandResultFormat
    list_models: str | bool
    list_models_format: ModelListFormat
    models: tuple[str, ...]
    extensions: tuple[str, ...]
    no_extensions: bool
    skills: tuple[str, ...]
    no_skills: bool
    prompt_templates: tuple[str, ...]
    no_prompt_templates: bool
    themes: tuple[str, ...]
    no_themes: bool
    api_key: str | None
    system_prompt: str | None
    append_system_prompt: tuple[str, ...]
    verbose: bool
    debug: str | None
    debug_file: str | None
    trace: str | None
    trace_file: str | None
    offline: bool
    export: str | None
    export_format: ExportFormat
    export_result_format: ExportResultFormat
    render_tool_events: bool
    work_log: str | None
    work_log_inspect: str | None
    work_log_run: str | None
    work_log_inspect_format: WorkLogInspectFormat
    messages: tuple[str, ...]
    file_args: tuple[str, ...]
    message_prompts: tuple[str, ...]
    unknown_flags: dict[str, bool | str]
    extension_flag_values: dict[str, bool | str]


def build_parser() -> ArgumentParser:
    return _build_parser()


def help_text() -> str:
    parser = _build_parser()
    return parser.format_help()


def parse_args(
    argv: list[str] | tuple[str, ...],
    *,
    extension_flags: Mapping[str, ExtensionFlag] | None = None,
    allow_unknown: bool = False,
) -> CliArgs:
    parser = _build_parser()
    registered_extension_flags: dict[str, ExtensionFlag] = {}
    for name, flag in dict(extension_flags or {}).items():
        if name in _BUILTIN_FLAG_NAMES:
            continue
        registered_extension_flags[name] = flag
        option = f"--{name}"
        dest = _extension_flag_dest(name)
        if flag.type == "boolean":
            parser.add_argument(option, dest=dest, action="store_true", default=None)
        else:
            parser.add_argument(option, dest=dest, default=None)

    raw_argv = _rewrite_observability_flags(
        _rewrite_package_subcommands(_rewrite_diag_subcommands(_rewrite_method_subcommands(list(argv))))
    )
    if allow_unknown:
        filtered_argv, unknown_flags = _extract_unknown_flags(
            raw_argv,
            known_flags=_BUILTIN_FLAG_NAMES | frozenset(registered_extension_flags),
        )
        namespace = parser.parse_intermixed_args(filtered_argv)
    else:
        namespace = parser.parse_intermixed_args(raw_argv)
        unknown_flags = {}

    extension_flag_values: dict[str, bool | str] = {}
    for name, flag in registered_extension_flags.items():
        value = getattr(namespace, _extension_flag_dest(name))
        if value is None:
            continue
        if flag.type == "boolean":
            extension_flag_values[name] = bool(value)
        elif isinstance(value, str):
            extension_flag_values[name] = value

    file_args, messages = _split_file_args(namespace.messages)
    return CliArgs(
        help=namespace.help,
        version=namespace.version,
        mode=namespace.mode,
        method=namespace.method,
        prompt=namespace.prompt,
        prompt_steps=namespace.prompt_steps,
        tui=namespace.tui,
        no_tui=namespace.no_tui,
        continue_=namespace.continue_,
        resume=namespace.resume,
        no_session=namespace.no_session,
        session=namespace.session,
        session_name=namespace.session_name,
        list_sessions=namespace.list_sessions,
        all_sessions=namespace.all_sessions,
        list_sessions_format=namespace.list_sessions_format,
        session_index=namespace.session_index,
        refresh_session_index=namespace.refresh_session_index,
        session_cwd=namespace.session_cwd,
        session_name_filter=namespace.session_name_filter,
        session_parent=namespace.session_parent,
        session_query=namespace.session_query,
        session_has_diagnostics=namespace.session_has_diagnostics,
        session_limit=namespace.session_limit,
        fork=namespace.fork,
        session_dir=namespace.session_dir,
        cwd=namespace.cwd,
        provider=namespace.provider,
        model=namespace.model,
        thinking=namespace.thinking,
        tools=_parse_tool_flags(namespace.tool_flags, namespace.tools),
        no_tools=namespace.no_tools,
        no_builtin_tools=namespace.no_builtin_tools,
        no_context_files=namespace.no_context_files,
        list_commands=namespace.list_commands,
        list_commands_format=namespace.list_commands_format,
        list_diagnostics=namespace.list_diagnostics,
        list_diagnostics_format=namespace.list_diagnostics_format,
        diagnostics_limit=namespace.diagnostics_limit,
        diag_export=namespace.diag_export,
        diag_output=namespace.diag_output,
        list_skills=namespace.list_skills,
        list_skills_format=namespace.list_skills_format,
        list_methods=namespace.list_methods,
        list_methods_format=namespace.list_methods_format,
        show_method=namespace.show_method,
        show_method_format=namespace.show_method_format,
        enable_skills=tuple(namespace.enable_skill),
        disable_skills=tuple(namespace.disable_skill),
        list_plugins=namespace.list_plugins,
        list_plugins_format=namespace.list_plugins_format,
        list_packages=namespace.list_packages,
        list_packages_format=namespace.list_packages_format,
        package_catalog=namespace.package_catalog,
        install_packages=tuple(namespace.install_package),
        uninstall_packages=tuple(namespace.uninstall_package),
        package_scope=namespace.package_scope,
        update_all_packages=namespace.update_packages,
        check_package_updates=namespace.check_package_updates,
        materialize_packages=tuple(namespace.materialize_package),
        update_packages=tuple(namespace.update_package),
        remove_packages=tuple(namespace.remove_package),
        add_plugin_sources=tuple(namespace.add_plugin_source),
        remove_plugin_sources=tuple(namespace.remove_plugin_source),
        enable_plugins=tuple(namespace.enable_plugin),
        disable_plugins=tuple(namespace.disable_plugin),
        command=namespace.command,
        command_args=namespace.command_args,
        command_result_format=namespace.command_result_format,
        list_models=namespace.list_models,
        list_models_format=namespace.list_models_format,
        models=tuple(_parse_csv_items(namespace.models)),
        extensions=tuple(namespace.extension),
        no_extensions=namespace.no_extensions,
        skills=tuple(namespace.skill),
        no_skills=namespace.no_skills,
        prompt_templates=tuple(namespace.prompt_template),
        no_prompt_templates=namespace.no_prompt_templates,
        themes=tuple(namespace.theme),
        no_themes=namespace.no_themes,
        api_key=namespace.api_key,
        system_prompt=namespace.system_prompt,
        append_system_prompt=tuple(_parse_csv_items_list(namespace.append_system_prompt)),
        verbose=namespace.verbose,
        debug=namespace.debug,
        debug_file=namespace.debug_file,
        trace=namespace.trace,
        trace_file=namespace.trace_file,
        offline=namespace.offline,
        export=namespace.export,
        export_format=namespace.export_format,
        export_result_format=namespace.export_result_format,
        render_tool_events=namespace.render_tool_events,
        work_log=namespace.work_log,
        work_log_inspect=namespace.work_log_inspect,
        work_log_run=namespace.work_log_run,
        work_log_inspect_format=namespace.work_log_inspect_format,
        messages=messages,
        file_args=file_args,
        message_prompts=tuple(namespace.message_prompts),
        unknown_flags=unknown_flags,
        extension_flag_values=extension_flag_values,
    )


def _build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m loushang.coding.cli",
        add_help=False,
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument("messages", nargs="*")
    parser.add_argument("--help", "-h", action="store_true")
    parser.add_argument("--version", "-v", action="store_true")
    parser.add_argument("--mode", choices=("text", "print", "json", "rpc"), default="text")
    parser.add_argument("--method", help="Guide one coding turn with a discovered method.")
    parser.add_argument(
        "--prompt",
        "-p",
        help="Run one coding prompt and render a stable transcript.",
    )
    parser.add_argument(
        "--prompt-steps",
        "-ps",
        help="Run a prompt workflow file against a coding session.",
    )
    parser.add_argument("--tui", action="store_true")
    parser.add_argument("--no-tui", action="store_true")
    parser.add_argument("--no-session", action="store_true")
    parser.add_argument("--session")
    parser.add_argument("--session-name")
    parser.add_argument("--list-sessions", action="store_true")
    parser.add_argument("--all-sessions", action="store_true")
    parser.add_argument("--list-sessions-format", choices=("tsv", "json"), default="tsv")
    parser.add_argument("--session-index", action="store_true")
    parser.add_argument("--refresh-session-index", action="store_true")
    parser.add_argument("--session-cwd")
    parser.add_argument("--session-name-filter")
    parser.add_argument("--session-parent")
    parser.add_argument("--session-query")
    parser.add_argument("--session-has-diagnostics", dest="session_has_diagnostics", action="store_true", default=None)
    parser.add_argument("--session-no-diagnostics", dest="session_has_diagnostics", action="store_false")
    parser.add_argument("--session-limit", type=int)
    parser.add_argument("--fork")
    parser.add_argument("--session-dir")
    parser.add_argument("--cwd")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--continue", "-c", dest="continue_", action="store_true")
    parser.add_argument("--resume", "-r", nargs="?", const=True, default=False, metavar="SESSION")
    parser.add_argument("--list-models", nargs="?", const="", default=False)
    parser.add_argument("--list-models-format", choices=("text", "json"), default="text")
    parser.add_argument("--models")
    parser.add_argument("--extension", "-e", action="append", default=[])
    parser.add_argument("--no-extensions", "-ne", action="store_true")
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--no-skills", "-ns", dest="no_skills", action="store_true")
    parser.add_argument("--prompt-template", action="append", default=[])
    parser.add_argument(
        "--no-prompt-templates",
        "-np",
        dest="no_prompt_templates",
        action="store_true",
    )
    parser.add_argument("--theme", action="append", default=[])
    parser.add_argument("--no-themes", action="store_true")
    parser.add_argument("--api-key")
    parser.add_argument("--system-prompt")
    parser.add_argument("--append-system-prompt", action="append", default=[])
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--debug", default=None)
    parser.add_argument("--debug-file")
    parser.add_argument("--trace", default=None)
    parser.add_argument("--trace-file")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--export", nargs="?", const="")
    parser.add_argument("--export-format", choices=("html", "jsonl"), default="html")
    parser.add_argument("--export-result-format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--render-tool-events",
        action="store_true",
        help="Attach renderedToolCall/renderedToolResult payloads to JSON/RPC tool events.",
    )
    parser.add_argument(
        "--work-log",
        help="Write WorkOperation/WorkEvent records for one-shot text/print/json prompts to a JSONL file.",
    )
    parser.add_argument(
        "--work-log-inspect",
        metavar="PATH",
        help="Inspect a work event JSONL log without starting a session.",
    )
    parser.add_argument("--work-log-run", help="Filter --work-log-inspect output to one run id.")
    parser.add_argument("--work-log-inspect-format", choices=("text", "json"), default="text")
    parser.add_argument("--message", dest="message_prompts", action="append", default=[])
    parser.add_argument("--tool", dest="tool_flags", action="append", default=[])
    parser.add_argument("--tools", "-t", dest="tools", action="append", default=[])
    parser.add_argument("--no-tools", "-nt", dest="no_tools", action="store_true")
    parser.add_argument("--no-builtin-tools", "-nbt", dest="no_builtin_tools", action="store_true")
    parser.add_argument(
        "--thinking",
        choices=("off", "minimal", "low", "medium", "high", "xhigh"),
    )
    parser.add_argument("--no-context-files", "-nc", dest="no_context_files", action="store_true")
    parser.add_argument("--list-commands", action="store_true")
    parser.add_argument("--list-commands-format", choices=("tsv", "json"), default="tsv")
    parser.add_argument("--list-diagnostics", action="store_true")
    parser.add_argument("--list-diagnostics-format", choices=("tsv", "json"), default="tsv")
    parser.add_argument("--diagnostics-limit", type=int, default=50)
    parser.add_argument("--diag-export", action="store_true")
    parser.add_argument("--diag-output")
    parser.add_argument("--list-skills", action="store_true")
    parser.add_argument("--list-skills-format", choices=("tsv", "json"), default="tsv")
    parser.add_argument("--list-methods", action="store_true")
    parser.add_argument("--list-methods-format", choices=("tsv", "json"), default="tsv")
    parser.add_argument("--show-method")
    parser.add_argument("--show-method-format", choices=("text", "json"), default="text")
    parser.add_argument("--enable-skill", action="append", default=[])
    parser.add_argument("--disable-skill", action="append", default=[])
    parser.add_argument("--list-plugins", action="store_true")
    parser.add_argument("--list-plugins-format", choices=("tsv", "json"), default="tsv")
    parser.add_argument("--list-packages", action="store_true")
    parser.add_argument("--list-packages-format", choices=("text", "tsv", "json"), default="text")
    parser.add_argument("--package-catalog")
    parser.add_argument("--install-package", action="append", default=[])
    parser.add_argument("--uninstall-package", action="append", default=[])
    parser.add_argument("--package-scope", choices=("global", "project"), default="global")
    parser.add_argument("--update-packages", action="store_true")
    parser.add_argument("--check-package-updates", action="store_true")
    parser.add_argument("--materialize-package", action="append", default=[])
    parser.add_argument("--update-package", action="append", default=[])
    parser.add_argument("--remove-package", action="append", default=[])
    parser.add_argument("--add-plugin-source", "--add-plugin", dest="add_plugin_source", action="append", default=[])
    parser.add_argument("--remove-plugin-source", "--remove-plugin", dest="remove_plugin_source", action="append", default=[])
    parser.add_argument("--enable-plugin", action="append", default=[])
    parser.add_argument("--disable-plugin", action="append", default=[])
    parser.add_argument("--command")
    parser.add_argument("--command-args", default="")
    parser.add_argument("--command-result-format", choices=("raw", "json"), default="raw")
    return parser


def _split_file_args(messages: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    file_args: list[str] = []
    plain_messages: list[str] = []
    for message in messages:
        if message.startswith("@") and len(message) > 1:
            file_args.append(message[1:])
        else:
            plain_messages.append(message)
    return tuple(file_args), tuple(plain_messages)


def _parse_tool_flags(tool_flags: list[str], tools_arg: list[str]) -> tuple[str, ...]:
    values: list[tuple[str, ...]] = []
    for flag in tool_flags:
        values.append(_parse_csv_items(flag))
    for group in tools_arg:
        values.append(_parse_csv_items(group))
    parsed: list[str] = []
    for values_group in values:
        parsed.extend(values_group)
    return tuple(parsed)


def _parse_csv_items(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(
        name.strip()
        for name in raw.split(",")
        if name.strip()
    )


def _parse_csv_items_list(raw: list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in raw:
        normalized.extend(_parse_csv_items(value))
    return tuple(normalized)


def _rewrite_package_subcommands(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    command = argv[0]
    if command == "list" and len(argv) == 1:
        return ["--list-packages"]
    if command not in {"install", "remove", "uninstall"}:
        return argv

    source: str | None = None
    trailing: list[str] = []
    scope = "global"
    for token in argv[1:]:
        if token in {"-l", "--local"}:
            scope = "project"
            continue
        if source is None:
            source = token
            continue
        trailing.append(token)
    if source is None or trailing:
        return argv

    flag = "--install-package" if command == "install" else "--uninstall-package"
    return [flag, source, "--package-scope", scope]


def _rewrite_method_subcommands(argv: list[str]) -> list[str]:
    method_index = _method_subcommand_index(argv)
    if method_index is None:
        return argv
    if len(argv) <= method_index + 1:
        return argv
    prefix = argv[:method_index]
    command = argv[method_index + 1]
    suffix = argv[method_index + 2 :]
    if command == "list":
        return [*prefix, "--list-methods", *suffix]
    if command == "show" and suffix:
        return [*prefix, "--show-method", suffix[0], *suffix[1:]]
    return argv


def _method_subcommand_index(argv: list[str]) -> int | None:
    if argv and argv[0] == "method":
        return 0
    if len(argv) >= 3 and argv[0] == "--cwd" and argv[2] == "method":
        return 2
    if len(argv) >= 2 and argv[0].startswith("--cwd=") and argv[1] == "method":
        return 1
    return None


def _rewrite_diag_subcommands(argv: list[str]) -> list[str]:
    if len(argv) < 2 or argv[0] != "diag" or argv[1] != "export":
        return argv

    rewritten = ["--diag-export"]
    index = 2
    while index < len(argv):
        token = argv[index]
        if token == "--output":
            rewritten.append("--diag-output")
            if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
                rewritten.append(argv[index + 1])
                index += 2
            else:
                index += 1
            continue
        if token.startswith("--output="):
            rewritten.append(f"--diag-output={token.split('=', 1)[1]}")
            index += 1
            continue
        rewritten.append(token)
        index += 1
    return rewritten


def _rewrite_observability_flags(argv: list[str]) -> list[str]:
    rewritten: list[str] = []
    for token in argv:
        if token == "--debug":
            rewritten.append("--debug=")
        elif token == "--trace":
            rewritten.append("--trace=all")
        else:
            rewritten.append(token)
    return rewritten


def _extension_flag_dest(name: str) -> str:
    return f"extension_flag_{name.replace('-', '_')}"


def _extract_unknown_flags(
    argv: list[str],
    *,
    known_flags: frozenset[str],
) -> tuple[list[str], dict[str, bool | str]]:
    filtered: list[str] = []
    unknown_flags: dict[str, bool | str] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if not token.startswith("--"):
            filtered.append(token)
            index += 1
            continue
        if "=" in token:
            name, value = token[2:].split("=", 1)
            if name in known_flags:
                filtered.append(token)
            else:
                unknown_flags[name] = value
            index += 1
            continue
        name = token[2:]
        if name in known_flags:
            filtered.append(token)
            index += 1
            continue
        if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            unknown_flags[name] = argv[index + 1]
            index += 2
            continue
        unknown_flags[name] = True
        index += 1
    return filtered, unknown_flags
