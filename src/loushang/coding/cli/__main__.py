from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr
from dataclasses import replace
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, TextIO, cast

from loushang.ai.model import (
    ModelSelection,
    model_selection_ref,
    parse_model_selection_reference,
)
from loushang.ai.model.registry import get_default_model_registry
from loushang.channel import ProductHostLifecycle, stream_is_tty
from loushang.coding.bootstrap import (
    BootstrapServices,
    create_agent_session_runtime,
    create_agent_session_services,
    create_services,
)
from loushang.coding.cli.args import CliArgs, ExtensionFlag, help_text, parse_args
from loushang.coding.control.settings_store import (
    default_global_settings_path,
    default_project_settings_path,
)
from loushang.coding.diag_export import export_diagnostics_bundle
from loushang.coding.domain import (
    CodingDomainApp,
    CodingDomainPreparedTurn,
    CodingDomainRequest,
    MethodPolicy,
)
from loushang.coding.mode import (
    ModeConfig,
    run_channel_mode,
    run_mode,
    run_print_mode,
    run_rpc_mode,
)
from loushang.coding.mode.print_mode import run_print_plan_mode
from loushang.coding.model_selection import (
    apply_model_selection,
    persistence_warning_message,
)
from loushang.coding.observability import (
    coding_observability_context,
    coding_startup_observability_context,
)
from loushang.coding.package_projection import collect_package_entries
from loushang.coding.policy import (
    ApprovalResolver,
    HeadlessApprovalResolver,
    InteractiveApprovalResolver,
    PackageSecurityPolicy,
    PolicyEngine,
)
from loushang.coding.prompt_command import (
    run_prompt_command,
    run_prompt_plan_command,
)
from loushang.coding.source_info import (
    executable_source_identity,
    format_source_identity_text,
)
from loushang.coding.tool_pack import register_coding_builtin_tools
from loushang.coding.ui.mode import run_coding_tui
from loushang.coding.work_executor import SubmitCodingTurn
from loushang.coding.work_runtime import CodingWorkRuntime
from loushang.coding.workflow import run_prompt_steps_workflow
from loushang.harness.cli import (
    CliLaunchPlan,
    CliOperationSequence,
    CliOperationStage,
    CommandExecutionRequest,
    DiagnosticsListingRequest,
    ExportRequest,
    MethodListingError,
    MethodListingRequest,
    ModelListingRequest,
    PackageLifecycleRequest,
    ResourceToggleRequest,
    SessionListingOperationRequest,
    SessionResolutionRequest,
    cli_help_belongs_on_stderr,
    cli_observability_mode,
    cli_output_guard_enabled,
    cli_runtime_error,
    cli_static_error,
    format_package_records,
    resolve_effective_tui,
    resolve_session,
    run_command_listing_operation,
    run_command_operation,
    run_diagnostics_listing_operation,
    run_export_operation,
    run_method_listing,
    run_model_listing_operation,
    run_package_lifecycle_operation,
    run_plugin_listing_operation,
    run_resource_toggle_operation,
    run_session_listing_operation,
    run_skill_listing_operation,
)
from loushang.harness.cli import (
    apply_extension_flag_values as apply_extension_flag_values_shared,
)
from loushang.harness.cli import (
    collect_extension_flags as collect_extension_flags_shared,
)
from loushang.harness.cli import (
    resolve_latest_session_file as resolve_latest_session_file_shared,
)
from loushang.harness.config.agent import SettingsManager
from loushang.harness.extensions.types import ResolvedFlag
from loushang.harness.host.prompt_input import (
    PromptInputPlan,
    resolve_prompt_input,
)
from loushang.harness.resources.plugins import is_remote_plugin_source
from loushang.harness.scenario.loader import load_workflow, resolve_workflow_files
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.method import MethodCompiler, MethodContext, MethodLoader
from loushang.work import (
    JsonlEventLogBackend,
    WorkLogInspectionError,
    inspect_work_log,
    resolve_work_log_path,
)

_MISSING = object()
_WORK_LOG_INSPECT_LIMIT = 20


PrintInputPlan = PromptInputPlan


def build_default_services(project_root: Path) -> BootstrapServices:
    settings_manager = SettingsManager(
        global_settings_path=default_global_settings_path(),
        project_settings_path=default_project_settings_path(project_root),
    )
    return create_services(
        ai_model_registry=get_default_model_registry(),
        settings_manager=settings_manager,
    )


def build_builtin_tool_registry(
    *,
    diagnostics_service: object | None = None,
    settings_manager: object | None = None,
    approval_resolver: ApprovalResolver | None = None,
) -> WorkspaceToolRegistry:
    registry = WorkspaceToolRegistry()
    tool_settings = _tool_settings_from_settings_manager(settings_manager)
    resolved_approval_resolver = (
        approval_resolver
        if approval_resolver is not None
        else _approval_resolver_from_tool_settings(tool_settings)
    )
    get_external_tool_policy = getattr(
        settings_manager, "get_external_tool_policy", None
    )
    register_coding_builtin_tools(
        registry,
        diagnostics_service=diagnostics_service,
        external_tool_policy=get_external_tool_policy()
        if callable(get_external_tool_policy)
        else None,
        policy_engine=_policy_engine_from_tool_settings(tool_settings),
        approval_resolver=resolved_approval_resolver,
    )
    return registry


def _tool_settings_from_settings_manager(
    settings_manager: object | None,
) -> object | None:
    get_tool_settings = getattr(settings_manager, "get_tool_settings", None)
    if callable(get_tool_settings):
        return get_tool_settings()
    get_settings = getattr(settings_manager, "get_settings", None)
    if callable(get_settings):
        return getattr(get_settings(), "tools", None)
    return None


def _policy_engine_from_tool_settings(
    tool_settings: object | None,
) -> PolicyEngine | None:
    if tool_settings is None:
        return None
    kwargs = {
        "blocked_tools": _tool_setting_tuple(tool_settings, "blocked_tools"),
        "ask_tools": _tool_setting_tuple(tool_settings, "ask_tools"),
        "blocked_substrings": _tool_setting_tuple(tool_settings, "blocked_substrings"),
        "ask_substrings": _tool_setting_tuple(tool_settings, "ask_substrings"),
        "blocked_path_substrings": _tool_setting_tuple(
            tool_settings, "blocked_path_substrings"
        ),
        "ask_path_substrings": _tool_setting_tuple(
            tool_settings, "ask_path_substrings"
        ),
    }
    if not any(kwargs.values()):
        return None
    return PolicyEngine(**kwargs)


def _approval_resolver_from_tool_settings(
    tool_settings: object | None,
) -> HeadlessApprovalResolver | None:
    if tool_settings is None:
        return None
    approval_mode = getattr(tool_settings, "approval_mode", None)
    if approval_mode is None:
        return None
    return HeadlessApprovalResolver(
        mode=approval_mode,
        reason=getattr(tool_settings, "approval_reason", None),
    )


def _tool_setting_tuple(tool_settings: object, name: str) -> tuple[str, ...]:
    value = getattr(tool_settings, name, ())
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def default_runtime_builder(
    *,
    args: CliArgs,
    cwd: Path,
    session_dir: Path,
    services: BootstrapServices,
    tool_registry: WorkspaceToolRegistry,
    approval_resolver: InteractiveApprovalResolver | None = None,
):
    if args.no_tools:
        allowed_tool_names = []
        active_tool_names = []
    elif args.tools:
        allowed_tool_names = list(args.tools)
        active_tool_names = list(args.tools)
    else:
        allowed_tool_names = None
        active_tool_names = None
    resource_loader_options = _resource_loader_options_from_args(args)
    _configure_resource_loader(services.resource_loader, resource_loader_options)
    services_factory = _cwd_bound_services_factory(services, resource_loader_options)
    return create_agent_session_runtime(
        session_dir=session_dir,
        services=services,
        services_factory=services_factory,
        tool_registry=tool_registry,
        allowed_tool_names=allowed_tool_names,
        active_tool_names=active_tool_names,
        persist=not args.no_session,
        approval_resolver=approval_resolver,
    )


def _invoke_runtime_builder(
    runtime_builder,
    *,
    args: CliArgs,
    cwd: Path,
    session_dir: Path,
    services: BootstrapServices,
    tool_registry: WorkspaceToolRegistry,
    approval_resolver: InteractiveApprovalResolver | None | object = _MISSING,
):
    kwargs = {
        "args": args,
        "cwd": cwd,
        "session_dir": session_dir,
        "services": services,
        "tool_registry": tool_registry,
    }
    if approval_resolver is not _MISSING and _accepts_keyword_argument(
        runtime_builder, "approval_resolver"
    ):
        kwargs["approval_resolver"] = approval_resolver
    return runtime_builder(**kwargs)


def _accepts_keyword_argument(callback: Any, name: str) -> bool:
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):
        return callback is default_runtime_builder
    parameter = parameters.get(name)
    if parameter is not None and parameter.kind in {
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    }:
        return True
    return any(
        candidate.kind is inspect.Parameter.VAR_KEYWORD
        for candidate in parameters.values()
    )


async def run_cli(
    argv: list[str] | tuple[str, ...] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    cwd: str | Path | None = None,
    services: BootstrapServices | Any | None = None,
    runtime_builder=default_runtime_builder,
    mode_runner=run_mode,
    prompt_runner=run_prompt_command,
    workflow_runner=run_prompt_steps_workflow,
    print_runner=run_print_mode,
    rpc_runner=run_rpc_mode,
    channel_runner=run_channel_mode,
    tui_runner=run_coding_tui,
) -> int:
    raw_argv = list(argv or ())
    host_lifecycle = ProductHostLifecycle.resolve(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
    streams = host_lifecycle.streams
    stdin = streams.stdin
    stdout = streams.stdout
    stderr = streams.stderr
    bootstrap_args, parse_error_code = _parse_args_for_cli(
        raw_argv,
        stderr=stderr,
        allow_unknown=True,
    )
    if bootstrap_args is None:
        return parse_error_code
    project_root = Path(cwd or bootstrap_args.cwd or Path.cwd()).resolve()
    _apply_offline_mode(bootstrap_args)
    bootstrap_launch_plan = _cli_launch_plan(bootstrap_args)

    if bootstrap_args.help:
        with host_lifecycle.output_guard(
            enabled=cli_output_guard_enabled(bootstrap_launch_plan)
        ):
            extension_flags = await _collect_extension_flags_for_help(
                raw_argv=raw_argv,
                project_root=project_root,
                services=services,
                runtime_builder=runtime_builder,
            )
        help_output = (
            stderr if cli_help_belongs_on_stderr(bootstrap_launch_plan) else stdout
        )
        help_output.write(_help_text(extension_flags))
        return 0
    if bootstrap_args.version:
        stdout.write(f"{_package_version()}\n")
        return 0
    if bootstrap_args.source_info:
        source_identity = executable_source_identity(cwd=project_root)
        if bootstrap_args.source_info_format == "json":
            stdout.write(json.dumps(source_identity, ensure_ascii=False) + "\n")
        else:
            stdout.write(format_source_identity_text(source_identity) + "\n")
        return 0

    static_error = cli_static_error(bootstrap_launch_plan)
    if static_error is not None:
        stderr.write(f"Error: {static_error}.\n")
        return 2
    work_log_inspect_result = _run_work_log_inspect(
        bootstrap_args, project_root, stdout, stderr
    )
    if work_log_inspect_result is not None:
        return work_log_inspect_result

    with host_lifecycle.output_guard(
        enabled=cli_output_guard_enabled(bootstrap_launch_plan)
    ):
        resolved_services = services or build_default_services(project_root)
        _report_settings_errors_for_resource_commands(
            bootstrap_args, resolved_services, stderr
        )
        resource_toggle_request = ResourceToggleRequest(
            enable_skills=tuple(bootstrap_args.enable_skills),
            disable_skills=tuple(bootstrap_args.disable_skills),
            add_plugin_sources=tuple(bootstrap_args.add_plugin_sources),
            remove_plugin_sources=tuple(bootstrap_args.remove_plugin_sources),
            enable_plugins=tuple(bootstrap_args.enable_plugins),
            disable_plugins=tuple(bootstrap_args.disable_plugins),
        )
        resource_toggle_result = run_resource_toggle_operation(
            getattr(resolved_services, "settings_manager", None),
            resource_toggle_request if resource_toggle_request.has_operations else None,
            stdout=stdout,
            stderr=stderr,
            evaluate_plugin_source=_package_source_policy_reason,
            is_remote_plugin_source=is_remote_plugin_source,
            on_policy_denied=lambda source, reason: _record_package_policy_diagnostic(
                resolved_services, source=source, reason=reason
            ),
            format_error=_format_cli_error,
        )
        if resource_toggle_result is not None:
            return resource_toggle_result
        runtime_args = _runtime_args_for_bootstrap(bootstrap_args)
        session_dir = _resolve_session_dir(
            runtime_args, project_root, resolved_services
        )
        diag_export_result = _run_diag_export(
            bootstrap_args,
            project_root,
            session_dir,
            resolved_services,
            stdout,
            stderr,
        )
        if diag_export_result is not None:
            return diag_export_result
        fake_workflow_result = await _run_fake_prompt_steps_workflow_if_requested(
            bootstrap_args,
            project_root=project_root,
            workflow_runner=workflow_runner,
            stdout=stdout,
            stderr=stderr,
        )
        if fake_workflow_result is not None:
            return fake_workflow_result
        settings_manager = getattr(resolved_services, "settings_manager", None)
        tool_settings = _tool_settings_from_settings_manager(settings_manager)
        configured_approval_resolver = _approval_resolver_from_tool_settings(
            tool_settings
        )
        interactive_approval_resolver: InteractiveApprovalResolver | None = None
        if configured_approval_resolver is None:
            interactive_approval_resolver = InteractiveApprovalResolver(
                fallback=HeadlessApprovalResolver(mode="deny")
            )
            approval_resolver: ApprovalResolver = interactive_approval_resolver
        else:
            approval_resolver = configured_approval_resolver
        if runtime_args.no_builtin_tools:
            tool_registry = WorkspaceToolRegistry()
        else:
            tool_registry = build_builtin_tool_registry(
                diagnostics_service=getattr(
                    resolved_services, "diagnostics_service", None
                ),
                settings_manager=getattr(resolved_services, "settings_manager", None),
                approval_resolver=approval_resolver,
            )

    with coding_startup_observability_context(
        args=bootstrap_args,
        services=resolved_services,
        cwd=project_root,
    ):
        with host_lifecycle.output_guard(
            enabled=cli_output_guard_enabled(bootstrap_launch_plan)
        ):
            runtime = _invoke_runtime_builder(
                runtime_builder,
                args=runtime_args,
                cwd=project_root,
                session_dir=session_dir,
                services=resolved_services,
                tool_registry=tool_registry,
                approval_resolver=interactive_approval_resolver,
            )
        runtime_launch_plan = _cli_launch_plan(runtime_args)
        with host_lifecycle.output_guard(
            enabled=cli_output_guard_enabled(runtime_launch_plan)
        ):
            list_sessions_result = run_session_listing_operation(
                runtime,
                SessionListingOperationRequest(
                    output_format=runtime_args.list_sessions_format,
                    cwd=runtime_args.session_cwd,
                    name=runtime_args.session_name_filter,
                    parent_session=runtime_args.session_parent,
                    text=runtime_args.session_query,
                    has_diagnostics=runtime_args.session_has_diagnostics,
                    limit=runtime_args.session_limit,
                    all_sessions=runtime_args.all_sessions,
                    indexed=runtime_args.session_index
                    or runtime_args.refresh_session_index,
                    refresh_index=runtime_args.refresh_session_index,
                )
                if runtime_args.list_sessions
                else None,
                stdout=stdout,
                stderr=stderr,
                format_error=_format_cli_error,
            )
        if list_sessions_result is not None:
            return list_sessions_result

        try:
            with host_lifecycle.output_guard(
                enabled=cli_output_guard_enabled(bootstrap_launch_plan)
            ):
                session = await _resolve_session(runtime_args, runtime, project_root)
        except (
            FileNotFoundError,
            NotADirectoryError,
            RuntimeError,
            ValueError,
        ) as error:
            stderr.write(f"Error: {_format_cli_error(error)}\n")
            return 1
    if session is None:
        return 2
    extension_flags = _collect_extension_flags(session)
    args, parse_error_code = _parse_args_for_cli(
        raw_argv,
        stderr=stderr,
        extension_flags=extension_flags,
    )
    if args is None:
        return parse_error_code
    launch_plan = _cli_launch_plan(args)
    with host_lifecycle.output_guard(enabled=cli_output_guard_enabled(launch_plan)):
        _apply_extension_flag_values(session, args.extension_flag_values)

        if args.session_name is not None:
            setter = getattr(session, "set_session_name", None)
            if callable(setter):
                setter(args.session_name)

        override_result = await _apply_model_and_thinking_overrides(
            args,
            session,
            stderr,
            settings_manager=settings_manager,
        )
        if override_result is not None:
            return override_result

        package_lifecycle_request = PackageLifecycleRequest(
            install=tuple(args.install_packages),
            materialize=tuple(args.materialize_packages),
            update=tuple(args.update_packages),
            remove=tuple(args.remove_packages),
            uninstall=tuple(args.uninstall_packages),
            check_updates=args.check_package_updates,
            update_all=args.update_all_packages,
            scope=args.package_scope,
        )
        model_listing_request = (
            ModelListingRequest(
                query=args.list_models.strip().lower()
                if isinstance(args.list_models, str)
                else ""
            )
            if args.list_models is not False
            else None
        )
        standard_operation_result = await CliOperationSequence(
            (
                CliOperationStage(
                    "export",
                    lambda: run_export_operation(
                        session,
                        ExportRequest(format=args.export_format, output=args.export)
                        if args.export is not None
                        else None,
                        result_format=args.export_result_format,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "list_commands",
                    lambda: run_command_listing_operation(
                        session,
                        args.list_commands_format if args.list_commands else None,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "list_diagnostics",
                    lambda: run_diagnostics_listing_operation(
                        session,
                        DiagnosticsListingRequest(limit=args.diagnostics_limit)
                        if args.list_diagnostics
                        else None,
                        output_format=args.list_diagnostics_format,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "list_skills",
                    lambda: run_skill_listing_operation(
                        session,
                        args.list_skills_format if args.list_skills else None,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "method_visibility",
                    lambda: _run_method_visibility(
                        args, project_root, stdout, stderr
                    ),
                ),
                CliOperationStage(
                    "list_plugins",
                    lambda: run_plugin_listing_operation(
                        getattr(resolved_services, "settings_manager", None),
                        args.list_plugins_format if args.list_plugins else None,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "list_packages",
                    lambda: _run_list_packages(
                        args,
                        session,
                        resolved_services,
                        project_root,
                        stdout,
                        stderr,
                    ),
                ),
                CliOperationStage(
                    "package_lifecycle",
                    lambda: run_package_lifecycle_operation(
                        session,
                        package_lifecycle_request
                        if package_lifecycle_request.has_operations
                        else None,
                        stdout=stdout,
                        stderr=stderr,
                        evaluate_install_source=_package_source_policy_reason,
                        on_policy_denied=lambda source, reason: (
                            _record_package_policy_diagnostic(
                                resolved_services, source=source, reason=reason
                            )
                        ),
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "command",
                    lambda: run_command_operation(
                        session,
                        CommandExecutionRequest(
                            command=args.command,
                            args=args.command_args,
                            result_format=args.command_result_format,
                        )
                        if args.command is not None
                        else None,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
                CliOperationStage(
                    "list_models",
                    lambda: run_model_listing_operation(
                        session,
                        model_listing_request,
                        output_format=args.list_models_format,
                        stdout=stdout,
                        stderr=stderr,
                        format_error=_format_cli_error,
                    ),
                ),
            )
        ).run()
        if standard_operation_result is not None:
            return standard_operation_result

        effective_tui = resolve_effective_tui(
            launch_plan,
            stdin_is_tty=stream_is_tty(stdin),
            stdout_is_tty=stream_is_tty(stdout),
        )
        runtime_error = cli_runtime_error(
            launch_plan,
            effective_tui=effective_tui,
        )
        if runtime_error is not None:
            stderr.write(f"Error: {runtime_error}.\n")
            return 2
        work_event_log = _resolve_work_event_log(args.work_log, project_root)
        coding_work_runtime = (
            CodingWorkRuntime(session=session, event_log=work_event_log)
            if work_event_log is not None
            else None
        )
        with coding_observability_context(
            args=args,
            session=session,
            cwd=project_root,
            mode=cli_observability_mode(launch_plan, effective_tui=effective_tui),
        ):
            if effective_tui:
                return await tui_runner(
                    runtime=runtime,
                    session=session,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    verbose=args.verbose,
                )

            if args.mode == "rpc":
                if args.file_args:
                    stderr.write(
                        "Error: @file arguments are not supported in RPC mode.\n"
                    )
                    return 2
                if rpc_runner is not run_rpc_mode:
                    return await rpc_runner(
                        runtime=runtime,
                        stdin=stdin,
                        stdout=stdout,
                        stderr=stderr,
                        render_tool_events=args.render_tool_events,
                    )
                return await mode_runner(
                    config=ModeConfig(
                        mode="rpc", render_tool_events=args.render_tool_events
                    ),
                    runtime=runtime,
                    session=session,
                    user_input=None,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                )

            if args.mode == "channel":
                return await channel_runner(
                    runtime=runtime,
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                )

            if args.prompt_steps is not None:
                return await workflow_runner(
                    runtime=runtime,
                    session=session,
                    workflow_path=Path(args.prompt_steps),
                    cwd=project_root,
                    stdout=stdout,
                    stderr=stderr,
                    verbose=args.verbose,
                    output_mode=_workflow_output_mode(args),
                )

            try:
                print_input = _resolve_print_input_plan(
                    args,
                    stdin,
                    project_root,
                    auto_resize_images=_get_image_auto_resize(resolved_services),
                )
            except (OSError, UnicodeDecodeError, RuntimeError) as error:
                stderr.write(f"Error: {_format_cli_error(error)}\n")
                return 1
            if print_input.user_input is None:
                stderr.write(
                    "Error: prompt is required for prompt/text/print/json modes.\n"
                )
                return 2

            try:
                prepared_turns = CodingDomainApp(cwd=project_root).prepare_turns(
                    CodingDomainRequest(
                        user_input=print_input.user_input,
                        cwd=project_root,
                        method_policy=_method_policy_from_args(
                            args, settings_manager=settings_manager
                        ),
                    )
                )
            except ValueError as error:
                stderr.write(f"Error: {_format_method_cli_error(error)}\n")
                return 1

            if args.prompt is not None:
                if (
                    prompt_runner is run_prompt_command
                    and work_event_log is not None
                    and len(prepared_turns) > 1
                ):
                    return await run_prompt_plan_command(
                        runtime=runtime,
                        session=session,
                        turns=_prepared_turns_to_work_turns(
                            prepared_turns,
                            images=print_input.images,
                            follow_up_messages=print_input.follow_up_messages,
                        ),
                        stdout=stdout,
                        stderr=stderr,
                        verbose=args.verbose,
                        work_event_log=work_event_log,
                        coding_work_runtime=coding_work_runtime,
                    )
                async def run_prompt_turn(
                    prepared_turn: CodingDomainPreparedTurn,
                    is_first_turn: bool,
                    is_last_turn: bool,
                ) -> int:
                    planned_constraint = _prepared_turn_policy_metadata(
                        prepared_turn, "planned_constraint"
                    )
                    audit_policy = _prepared_turn_policy_metadata(
                        prepared_turn, "audit_policy"
                    )
                    plan_facts = _prepared_turn_policy_metadata(
                        prepared_turn, "plan_facts"
                    )
                    step_facts = _prepared_turn_policy_metadata(
                        prepared_turn, "step_facts"
                    )
                    return await prompt_runner(
                        runtime=runtime,
                        session=session,
                        prompt=prepared_turn.prepared_prompt,
                        stdout=stdout,
                        stderr=stderr,
                        images=print_input.images if is_first_turn else None,
                        follow_up_messages=print_input.follow_up_messages
                        if is_last_turn
                        else (),
                        verbose=args.verbose,
                        work_event_log=work_event_log,
                        coding_work_runtime=coding_work_runtime,
                        method_id=prepared_turn.method_id,
                        plan_id=prepared_turn.plan_id,
                        step_id=prepared_turn.step_id,
                        step_index=prepared_turn.step_index,
                        step_title=prepared_turn.step_title,
                        planned_constraint=planned_constraint,
                        audit_policy=audit_policy,
                        plan_facts=plan_facts,
                        step_facts=step_facts,
                        dispose=is_last_turn,
                    )

                return await host_lifecycle.run_turns(
                    prepared_turns,
                    run_turn=run_prompt_turn,
                    dispose_candidates=(runtime, session),
                )

            output_mode = "text" if args.mode == "print" else args.mode
            if print_runner is not run_print_mode:
                async def run_print_turn(
                    prepared_turn: CodingDomainPreparedTurn,
                    is_first_turn: bool,
                    is_last_turn: bool,
                ) -> int:
                    planned_constraint = _prepared_turn_policy_metadata(
                        prepared_turn, "planned_constraint"
                    )
                    audit_policy = _prepared_turn_policy_metadata(
                        prepared_turn, "audit_policy"
                    )
                    plan_facts = _prepared_turn_policy_metadata(
                        prepared_turn, "plan_facts"
                    )
                    step_facts = _prepared_turn_policy_metadata(
                        prepared_turn, "step_facts"
                    )
                    return await print_runner(
                        runtime=runtime,
                        session=session,
                        user_input=prepared_turn.prepared_prompt,
                        stdout=stdout,
                        stderr=stderr,
                        images=print_input.images if is_first_turn else None,
                        follow_up_messages=print_input.follow_up_messages
                        if is_last_turn
                        else (),
                        output_mode=output_mode,
                        render_tool_events=args.render_tool_events,
                        work_event_log=work_event_log,
                        method_id=prepared_turn.method_id,
                        plan_id=prepared_turn.plan_id,
                        step_id=prepared_turn.step_id,
                        step_index=prepared_turn.step_index,
                        step_title=prepared_turn.step_title,
                        planned_constraint=planned_constraint,
                        audit_policy=audit_policy,
                        plan_facts=plan_facts,
                        step_facts=step_facts,
                        dispose=is_last_turn,
                    )

                return await host_lifecycle.run_turns(
                    prepared_turns,
                    run_turn=run_print_turn,
                    dispose_candidates=(runtime, session),
                )

            if (
                mode_runner is run_mode
                and work_event_log is not None
                and len(prepared_turns) > 1
            ):
                return await run_print_plan_mode(
                    runtime=runtime,
                    session=session,
                    turns=_prepared_turns_to_work_turns(
                        prepared_turns,
                        images=print_input.images,
                        follow_up_messages=print_input.follow_up_messages,
                    ),
                    stdout=stdout,
                    stderr=stderr,
                    output_mode=output_mode,
                    render_tool_events=args.render_tool_events,
                    work_event_log=work_event_log,
                    coding_work_runtime=coding_work_runtime,
                )

            async def run_mode_turn(
                prepared_turn: CodingDomainPreparedTurn,
                is_first_turn: bool,
                is_last_turn: bool,
            ) -> int:
                planned_constraint = _prepared_turn_policy_metadata(
                    prepared_turn, "planned_constraint"
                )
                audit_policy = _prepared_turn_policy_metadata(
                    prepared_turn, "audit_policy"
                )
                plan_facts = _prepared_turn_policy_metadata(prepared_turn, "plan_facts")
                step_facts = _prepared_turn_policy_metadata(prepared_turn, "step_facts")
                return await mode_runner(
                    config=ModeConfig(
                        mode=args.mode,
                        render_tool_events=args.render_tool_events,
                    ),
                    runtime=runtime,
                    session=session,
                    user_input=prepared_turn.prepared_prompt,
                    images=print_input.images if is_first_turn else None,
                    follow_up_messages=print_input.follow_up_messages
                    if is_last_turn
                    else (),
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    work_event_log=work_event_log,
                    coding_work_runtime=coding_work_runtime,
                    method_id=prepared_turn.method_id,
                    plan_id=prepared_turn.plan_id,
                    step_id=prepared_turn.step_id,
                    step_index=prepared_turn.step_index,
                    step_title=prepared_turn.step_title,
                    planned_constraint=planned_constraint,
                    audit_policy=audit_policy,
                    plan_facts=plan_facts,
                    step_facts=step_facts,
                    dispose=is_last_turn,
                )

            return await host_lifecycle.run_turns(
                prepared_turns,
                run_turn=run_mode_turn,
                dispose_candidates=(runtime, session),
            )


def _prepared_turn_policy_metadata(
    prepared_turn: Any, key: str
) -> Mapping[str, object] | None:
    value = prepared_turn.metadata.get(key)
    if isinstance(value, Mapping) and value:
        return dict(value)
    return None


def _prepared_turns_to_work_turns(
    prepared_turns: tuple[CodingDomainPreparedTurn, ...],
    *,
    images: Sequence[object] | None,
    follow_up_messages: tuple[str, ...],
) -> tuple[SubmitCodingTurn, ...]:
    turns: list[SubmitCodingTurn] = []
    for index, prepared_turn in enumerate(prepared_turns):
        turns.append(
            SubmitCodingTurn(
                text=prepared_turn.prepared_prompt,
                images=images if index == 0 else None,
                method_id=prepared_turn.method_id,
                plan_id=prepared_turn.plan_id,
                step_id=prepared_turn.step_id,
                step_index=prepared_turn.step_index,
                step_title=prepared_turn.step_title,
                planned_constraint=_prepared_turn_policy_metadata(
                    prepared_turn, "planned_constraint"
                ),
                audit_policy=_prepared_turn_policy_metadata(
                    prepared_turn, "audit_policy"
                ),
                plan_facts=_prepared_turn_policy_metadata(prepared_turn, "plan_facts"),
                step_facts=_prepared_turn_policy_metadata(prepared_turn, "step_facts"),
                follow_up_messages=follow_up_messages
                if index == len(prepared_turns) - 1
                else (),
            )
        )
    return tuple(turns)


def _resolve_session_dir(args: CliArgs, project_root: Path, services: Any) -> Path:
    if args.session_dir:
        return Path(args.session_dir).expanduser().resolve()
    settings = services.settings_manager.get_settings()
    configured = getattr(settings, "session_dir", None)
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root / ".loushang" / "sessions"


def _get_image_auto_resize(services: Any) -> bool:
    settings_manager = getattr(services, "settings_manager", None)
    get_image_auto_resize = getattr(settings_manager, "get_image_auto_resize", None)
    if callable(get_image_auto_resize):
        return bool(get_image_auto_resize())
    get_settings = getattr(settings_manager, "get_settings", None)
    if not callable(get_settings):
        return True
    settings = get_settings()
    images = getattr(settings, "images", None)
    if images is None:
        return True
    return bool(getattr(images, "auto_resize", True))


def _apply_offline_mode(args: CliArgs) -> None:
    if args.offline:
        os.environ["LOUSHANG_OFFLINE"] = "1"


def _configure_resource_loader_from_args(
    resource_loader: object, args: CliArgs
) -> None:
    _configure_resource_loader(
        resource_loader, _resource_loader_options_from_args(args)
    )


def _resource_loader_options_from_args(args: CliArgs) -> dict[str, object]:
    options: dict[str, object] = {
        "additional_extension_paths": list(getattr(args, "extensions", ())),
        "additional_skill_paths": list(getattr(args, "skills", ())),
        "additional_prompt_template_paths": list(getattr(args, "prompt_templates", ())),
        "additional_theme_paths": list(getattr(args, "themes", ())),
        "no_extensions": bool(getattr(args, "no_extensions", False)),
        "no_skills": bool(getattr(args, "no_skills", False)),
        "no_prompt_templates": bool(getattr(args, "no_prompt_templates", False)),
        "no_themes": bool(getattr(args, "no_themes", False)),
        "no_context_files": bool(getattr(args, "no_context_files", False)),
    }
    if hasattr(args, "system_prompt"):
        options["system_prompt"] = getattr(args, "system_prompt")
    if hasattr(args, "append_system_prompt"):
        options["append_system_prompt"] = list(getattr(args, "append_system_prompt"))
    return options


def _configure_resource_loader(
    resource_loader: object, options: dict[str, object]
) -> None:
    setter = getattr(resource_loader, "set_runtime_options", None)
    if not callable(setter):
        return
    setter(**options)


def _cwd_bound_services_factory(
    services: BootstrapServices, resource_loader_options: dict[str, object]
):
    project_base_dir = getattr(
        getattr(services, "settings_manager", None), "project_base_dir", None
    )
    if project_base_dir is None:
        return None

    def build_for_cwd(cwd: str) -> BootstrapServices:
        return create_agent_session_services(
            cwd=cwd,
            resource_loader_options=resource_loader_options,
        ).services

    return build_for_cwd


def _cli_launch_plan(args: CliArgs) -> CliLaunchPlan:
    command_operations = (
        args.list_sessions,
        args.source_info,
        args.list_models is not False,
        args.list_commands,
        args.list_diagnostics,
        args.list_skills,
        args.list_methods,
        args.show_method is not None,
        args.show_method_plan is not None,
        args.list_plugins,
        args.list_packages,
        args.export is not None,
        args.diag_export,
        args.command is not None,
        bool(args.enable_skills),
        bool(args.disable_skills),
        bool(args.add_plugin_sources),
        bool(args.remove_plugin_sources),
        bool(args.enable_plugins),
        bool(args.disable_plugins),
        bool(args.install_packages),
        bool(args.uninstall_packages),
        bool(args.materialize_packages),
        bool(args.update_packages),
        bool(args.remove_packages),
        args.update_all_packages,
        args.check_package_updates,
        args.work_log_inspect is not None,
    )
    structured_operations = (
        args.list_sessions and args.list_sessions_format == "json",
        args.list_models is not False and args.list_models_format == "json",
        args.list_commands and args.list_commands_format == "json",
        args.list_diagnostics and args.list_diagnostics_format == "json",
        args.list_skills and args.list_skills_format == "json",
        args.list_methods and args.list_methods_format == "json",
        args.show_method is not None and args.show_method_format == "json",
        args.show_method_plan is not None
        and args.show_method_plan_format == "json",
        args.list_plugins and args.list_plugins_format == "json",
        args.list_packages and args.list_packages_format == "json",
        args.export is not None and args.export_result_format == "json",
        args.command is not None and args.command_result_format == "json",
        bool(args.materialize_packages),
        bool(args.update_packages),
        bool(args.remove_packages),
        args.update_all_packages,
        args.check_package_updates,
    )
    return CliLaunchPlan(
        mode=args.mode,
        force_tui=args.tui,
        disable_tui=args.no_tui,
        prompt_requested=args.prompt is not None,
        workflow_requested=args.prompt_steps is not None,
        message_input=bool(args.messages),
        file_input=bool(args.file_args),
        follow_up_input=bool(args.message_prompts),
        render_tool_events=args.render_tool_events,
        work_log_requested=args.work_log is not None,
        method_requested=args.method is not None,
        method_disabled=args.no_method,
        session_requested=args.session is not None,
        continue_requested=args.continue_,
        resume_requested=args.resume,
        fork_requested=args.fork is not None,
        command_operation=any(command_operations),
        structured_operation_output=any(structured_operations),
    )


async def _run_fake_prompt_steps_workflow_if_requested(
    args: CliArgs,
    *,
    project_root: Path,
    workflow_runner,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if args.prompt_steps is None:
        return None
    try:
        workflow_files = resolve_workflow_files(project_root, args.prompt_steps)
        workflows = [load_workflow(workflow_file) for workflow_file in workflow_files]
    except Exception as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    if not workflows or any(workflow.backend != "fake" for workflow in workflows):
        return None
    return await workflow_runner(
        runtime=None,
        session=None,
        workflow_path=Path(args.prompt_steps),
        cwd=project_root,
        stdout=stdout,
        stderr=stderr,
        verbose=args.verbose,
        output_mode=_workflow_output_mode(args),
    )


def _workflow_output_mode(args: CliArgs) -> str:
    return "json" if args.mode == "json" else "text"


def _method_policy_from_args(
    args: CliArgs,
    *,
    settings_manager: object | None = None,
) -> MethodPolicy:
    if args.no_method:
        return MethodPolicy.off()
    if args.method is not None:
        return MethodPolicy.explicit(args.method)
    method_settings = _method_settings_from_settings_manager(settings_manager)
    if method_settings is None:
        return MethodPolicy.explicit(None)
    if getattr(method_settings, "mode", None) == "off":
        return MethodPolicy.off()
    return MethodPolicy(
        mode=getattr(method_settings, "mode", "explicit"),
        selected_method=getattr(method_settings, "selected_method", None),
    )


def _method_settings_from_settings_manager(
    settings_manager: object | None,
) -> object | None:
    get_method_settings = getattr(settings_manager, "get_method_settings", None)
    if callable(get_method_settings):
        return get_method_settings()
    get_settings = getattr(settings_manager, "get_settings", None)
    if callable(get_settings):
        return getattr(get_settings(), "method", None)
    return None


def _resolve_work_event_log(
    raw_path: str | None, project_root: Path
) -> JsonlEventLogBackend | None:
    if raw_path is None:
        return None
    return JsonlEventLogBackend(_resolve_work_log_path(raw_path, project_root))


def _run_work_log_inspect(
    args: CliArgs, project_root: Path, stdout: TextIO, stderr: TextIO
) -> int | None:
    if args.work_log_inspect is None:
        return None
    try:
        output = inspect_work_log(
            args.work_log_inspect,
            project_root=project_root,
            run_id=args.work_log_run,
            output_format=args.work_log_inspect_format,
            limit=_WORK_LOG_INSPECT_LIMIT,
        )
    except WorkLogInspectionError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(output)
    return 0


def _resolve_work_log_path(raw_path: str, project_root: Path) -> Path:
    return resolve_work_log_path(raw_path, project_root)


def _parse_args_for_cli(
    argv: list[str],
    *,
    stderr: TextIO,
    extension_flags: Mapping[str, ExtensionFlag] | None = None,
    allow_unknown: bool = False,
) -> tuple[CliArgs | None, int]:
    try:
        with redirect_stderr(stderr):
            return (
                parse_args(
                    argv,
                    extension_flags=extension_flags,
                    allow_unknown=allow_unknown,
                ),
                0,
            )
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 2
        return None, code


def _format_cli_error(error: BaseException) -> str:
    filename = getattr(error, "filename", None)
    if isinstance(error, OSError):
        strerror = getattr(error, "strerror", None)
        if filename is not None and strerror:
            return f"{strerror}: {filename}"
    return str(error)


def _format_method_cli_error(error: ValueError) -> str:
    message = _format_cli_error(error)
    if message.startswith("method not found:"):
        return f"{message}\nRun 'loushang method list' to inspect available methods."
    return message


def _runtime_args_for_bootstrap(args: CliArgs) -> CliArgs:
    if (
        args.list_commands
        or args.list_diagnostics
        or args.list_skills
        or args.list_methods
        or args.show_method is not None
        or args.show_method_plan is not None
        or args.list_plugins
        or args.list_packages
        or args.list_models is not False
        or args.enable_skills
        or args.disable_skills
        or args.add_plugin_sources
        or args.remove_plugin_sources
        or args.enable_plugins
        or args.disable_plugins
    ):
        return replace(args, no_session=True)
    return args


def _report_settings_errors_for_resource_commands(
    args: CliArgs, services: Any, stderr: TextIO
) -> None:
    if not (
        args.list_plugins
        or args.list_packages
        or args.enable_skills
        or args.disable_skills
        or args.add_plugin_sources
        or args.remove_plugin_sources
        or args.enable_plugins
        or args.disable_plugins
    ):
        return
    settings_manager = getattr(services, "settings_manager", None)
    context = (
        "package command"
        if args.list_packages
        or args.list_plugins
        or args.add_plugin_sources
        or args.remove_plugin_sources
        else "settings command"
    )
    _report_settings_errors(settings_manager, context=context, stderr=stderr)


def _report_settings_errors(
    settings_manager: Any, *, context: str, stderr: TextIO
) -> None:
    drain_errors = getattr(settings_manager, "drain_errors", None)
    if not callable(drain_errors):
        return
    try:
        errors = drain_errors()
    except Exception:
        return
    if not isinstance(errors, list):
        return
    for error in errors:
        scope = _safe_getattr(error, "scope", "unknown")
        message = _safe_getattr(error, "message", "")
        stderr.write(f"Warning ({context}, {scope} settings): {message}\n")


def _record_package_policy_diagnostic(
    services: Any, *, source: str, reason: str | None
) -> None:
    diagnostics = getattr(services, "diagnostics_service", None)
    capture_failure = getattr(diagnostics, "capture_failure", None)
    if not callable(capture_failure):
        return
    capture_failure(
        code="package_source_policy_denied",
        error=reason or "Package source denied by policy.",
        phase="runtime",
        source="policy",
        details={
            "plugin_source": source,
            "policy": "package_security",
            "disposition": "deny",
        },
    )


async def _resolve_session(args: CliArgs, runtime: Any, project_root: Path):
    return await resolve_session(
        runtime,
        SessionResolutionRequest(
            session=args.session,
            continue_=args.continue_,
            resume=args.resume,
            fork=args.fork,
            cwd=project_root,
        ),
    )


def _resolve_latest_session_file(runtime: Any) -> str | None:
    return resolve_latest_session_file_shared(runtime)


def _resolve_model_selection(args: CliArgs) -> ModelSelection | None:
    return parse_model_selection_reference(args.model, provider=args.provider)


async def _apply_model_and_thinking_overrides(
    args: CliArgs,
    session: Any,
    stderr: TextIO,
    *,
    settings_manager: object | None = None,
) -> int | None:
    try:
        explicit_model = _resolve_model_selection(args)
        if explicit_model is not None:
            result = await apply_model_selection(
                session,
                explicit_model,
                settings_manager=settings_manager,
            )
            if warning := persistence_warning_message(result):
                stderr.write(
                    f"Warning: Model changed to {model_selection_ref(result.selection)}, "
                    f"but {warning}\n"
                )
        if args.thinking is not None:
            thinking_result = session.set_thinking_level(args.thinking)
            if inspect.isawaitable(thinking_result):
                await thinking_result
    except (RuntimeError, ValueError) as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    return None


def _run_diag_export(
    args: CliArgs,
    project_root: Path,
    session_dir: Path,
    services: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.diag_export:
        return None

    try:
        output_path = export_diagnostics_bundle(
            project_root=project_root,
            session_dir=session_dir,
            output=args.diag_output,
            diagnostics_service=getattr(services, "diagnostics_service", None),
            debug_latest_path=args.debug_file,
            trace_latest_path=args.trace_file,
        )
    except Exception as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1

    stdout.write(f"Exported diagnostics to: {output_path}\n")
    return 0


def _safe_getattr(target: Any, name: str, default: object) -> object:
    try:
        return getattr(target, name, default)
    except Exception:
        return default


def _resolve_print_input_plan(
    args: CliArgs,
    stdin: TextIO,
    cwd: Path,
    *,
    auto_resize_images: bool = True,
) -> PrintInputPlan:
    return resolve_prompt_input(
        prompt=args.prompt,
        messages=tuple(args.messages),
        message_prompts=tuple(args.message_prompts),
        file_args=tuple(args.file_args),
        stdin=stdin,
        cwd=cwd,
        auto_resize_images=auto_resize_images,
    )


def _collect_extension_flags(session: Any) -> dict[str, ResolvedFlag]:
    return cast(dict[str, ResolvedFlag], collect_extension_flags_shared(session))


def _apply_extension_flag_values(session: Any, values: dict[str, bool | str]) -> None:
    apply_extension_flag_values_shared(session, values)


def _run_method_visibility(
    args: CliArgs,
    project_root: Path,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if (
        not args.list_methods
        and args.show_method is None
        and args.show_method_plan is None
    ):
        return None

    request = MethodListingRequest(
        list_methods=args.list_methods,
        list_format=args.list_methods_format,
        show_method=args.show_method,
        show_format=args.show_method_format,
        show_method_plan=args.show_method_plan,
        show_plan_format=args.show_method_plan_format,
    )
    if not request.has_operation:
        return None
    try:
        result = run_method_listing(
            request,
            discover_methods=lambda: MethodLoader().discover_methods(project_root),
            compile_plan=lambda method: MethodCompiler().compile(
                method, context=MethodContext(domain="coding")
            ),
        )
    except MethodListingError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(result.output)
    return 0


def _run_list_packages(
    args: CliArgs,
    session: Any,
    services: Any,
    project_root: Path,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.list_packages:
        return None

    get_packages = getattr(session, "get_packages", None)
    if not callable(get_packages):
        stderr.write("Error: package listing is not available.\n")
        return 1
    try:
        packages = get_packages(catalog_path=args.package_catalog)
        if not packages:
            settings_manager = getattr(services, "settings_manager", None)
            get_settings = getattr(settings_manager, "get_settings", None)
            if callable(get_settings):
                settings = get_settings()
                packages = collect_package_entries(
                    package_roots=tuple(getattr(settings, "package_roots", ())),
                    plugin_sources=tuple(getattr(settings, "plugin_sources", ())),
                    package_sources=tuple(getattr(settings, "package_sources", ())),
                    disabled_plugins=tuple(getattr(settings, "disabled_plugins", ())),
                    cwd=project_root,
                    settings_manager=settings_manager,
                    catalog_path=Path(args.package_catalog).expanduser().resolve()
                    if args.package_catalog
                    else None,
                    materializer=getattr(session, "_package_materializer", None),
                )
    except Exception as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1

    if args.list_packages_format == "json":
        output_format = "json"
    elif args.list_packages_format == "tsv":
        output_format = "tsv"
    else:
        output_format = "text"
    stdout.write(format_package_records(packages, output_format))
    return 0


def _package_source_policy_reason(source: str) -> str | None:
    decision = PackageSecurityPolicy().evaluate_package_source(source)
    if decision.disposition == "deny":
        return decision.reason or "Package source denied by policy."
    return None


def _safe_string(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        try:
            return repr(value)
        except Exception:
            return ""


async def _collect_extension_flags_for_help(
    *,
    raw_argv: list[str],
    project_root: Path,
    services: BootstrapServices | Any | None = None,
    runtime_builder=default_runtime_builder,
) -> dict[str, ExtensionFlag]:
    bootstrap_args = replace(
        parse_args(raw_argv, allow_unknown=True),
        fork=None,
        no_session=True,
    )
    resolved_services = services or build_default_services(project_root)
    try:
        session_dir = _resolve_session_dir(
            bootstrap_args, project_root, resolved_services
        )
        if bootstrap_args.no_builtin_tools:
            tool_registry = WorkspaceToolRegistry()
        else:
            tool_registry = build_builtin_tool_registry(
                diagnostics_service=getattr(
                    resolved_services, "diagnostics_service", None
                ),
                settings_manager=getattr(resolved_services, "settings_manager", None),
            )
        runtime = _invoke_runtime_builder(
            runtime_builder,
            args=bootstrap_args,
            cwd=project_root,
            session_dir=session_dir,
            services=resolved_services,
            tool_registry=tool_registry,
            approval_resolver=None,
        )
        session = await _resolve_session(bootstrap_args, runtime, project_root)
        if session is None:
            return {}
        return _collect_extension_flags(session)
    except Exception:
        return {}


def _help_text(extension_flags: Mapping[str, ExtensionFlag] | None = None) -> str:
    text = help_text().rstrip()
    if text.startswith("usage:"):
        text = "Usage:" + text[len("usage:") :]
    if extension_flags:
        text += "\n\nExtension flags:"
        for flag_name in sorted(extension_flags):
            flag = extension_flags[flag_name]
            line = f"\n  --{flag_name} [{flag.type}]"
            if flag.description:
                line += f": {flag.description}"
            if flag.default is not None:
                line += f" (default={flag.default!r})"
            text += line
    return (
        text + "\n\n"
        "Output formats:\n"
        "  --list-models-format text|json controls --list-models output.\n"
        "  --list-sessions-format tsv|json controls --list-sessions output; --all-sessions searches across session dirs.\n"
        "  --list-commands-format tsv|json controls --list-commands output.\n"
        "  --list-skills-format tsv|json controls --list-skills output.\n"
        "  --list-plugins-format tsv|json controls --list-plugins output.\n"
        "  --list-packages-format text|tsv|json controls --list-packages output.\n"
        "  --enable-skill/--disable-skill persist project skill toggles.\n"
        "  --add-plugin-source/--remove-plugin-source persist project plugin sources.\n"
        "  --enable-plugin/--disable-plugin persist project plugin toggles.\n"
        "  --command-result-format raw|json controls --command result output.\n"
        "  --export-format html|jsonl controls exported session file type.\n"
        "  --export-result-format text|json controls --export CLI result output.\n"
        "  diag export --output PATH writes a diagnostics bundle without starting a model session.\n"
        + "\n\n"
        "Note:\n"
        "  Extensions can register additional flags. For extension-specific help, run\n"
        "  the extension docs or check extension output directly.\n"
    )


def _package_version() -> str:
    try:
        return package_version("loushang")
    except PackageNotFoundError:
        return "0.1.0"


def main(argv: list[str] | tuple[str, ...] | None = None) -> int:
    try:
        return asyncio.run(run_cli(sys.argv[1:] if argv is None else argv))
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted.\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
