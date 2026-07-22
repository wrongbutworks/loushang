from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr
from dataclasses import asdict, replace
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
from loushang.coding.control import SettingsManager
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
from loushang.harness.agent_transcript.catalog import project_session_record
from loushang.harness.cli import (
    CommandExecutionError,
    CommandExecutionRequest,
    CommandListingError,
    DiagnosticsListingError,
    DiagnosticsListingRequest,
    ExportOperationError,
    ExportRequest,
    ModelListingError,
    ModelListingRequest,
    PackageLifecycleError,
    PackageLifecycleRequest,
    PluginListingError,
    ResourceToggleError,
    ResourceToggleRequest,
    SessionListingError,
    SessionListingRequest,
    SessionResolutionRequest,
    SkillListingError,
    apply_resource_toggles,
    build_session_query,
    execute_command,
    export_session,
    format_command_execution_result,
    format_command_records,
    format_diagnostic_records,
    format_export_result,
    format_package_records,
    format_plugin_records,
    format_session_records,
    format_skill_records,
    list_command_records,
    list_diagnostic_records,
    list_model_entries,
    list_plugin_records,
    list_session_records,
    list_skill_records,
    resolve_session,
    run_package_lifecycle,
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
from loushang.harness.extensions.types import ResolvedFlag
from loushang.harness.host.prompt_input import (
    PromptInputPlan,
    resolve_prompt_input,
)
from loushang.harness.resources.plugins import is_remote_plugin_source
from loushang.harness.scenario.loader import load_workflow, resolve_workflow_files
from loushang.harness.session.model_selection import format_model_metadata_table
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.method import MethodCompiler, MethodContext, MethodLoader
from loushang.work import JsonlEventLogBackend, project_work_plan_runs

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

    if bootstrap_args.help:
        with host_lifecycle.output_guard(enabled=_stdout_guard_enabled(bootstrap_args)):
            extension_flags = await _collect_extension_flags_for_help(
                raw_argv=raw_argv,
                project_root=project_root,
                services=services,
                runtime_builder=runtime_builder,
            )
        help_output = stderr if _help_belongs_on_stderr(bootstrap_args) else stdout
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

    if bootstrap_args.tui and bootstrap_args.no_tui:
        stderr.write("Error: --tui and --no-tui cannot be used together.\n")
        return 2
    if bootstrap_args.fork and not (
        bootstrap_args.session or bootstrap_args.continue_ or bootstrap_args.resume
    ):
        stderr.write("Error: --fork requires --session or --continue / --resume.\n")
        return 2
    if bootstrap_args.session and (bootstrap_args.continue_ or bootstrap_args.resume):
        stderr.write("Error: --session cannot be used with --continue or --resume.\n")
        return 2
    if bootstrap_args.continue_ and bootstrap_args.resume:
        stderr.write("Error: --continue and --resume cannot be used together.\n")
        return 2
    work_log_error = _work_log_static_error(bootstrap_args)
    if work_log_error is not None:
        stderr.write(f"Error: {work_log_error}.\n")
        return 2
    method_error = _method_static_error(bootstrap_args)
    if method_error is not None:
        stderr.write(f"Error: {method_error}.\n")
        return 2
    channel_error = _channel_static_error(bootstrap_args)
    if channel_error is not None:
        stderr.write(f"Error: {channel_error}.\n")
        return 2
    work_log_inspect_result = _run_work_log_inspect(
        bootstrap_args, project_root, stdout, stderr
    )
    if work_log_inspect_result is not None:
        return work_log_inspect_result

    with host_lifecycle.output_guard(enabled=_stdout_guard_enabled(bootstrap_args)):
        resolved_services = services or build_default_services(project_root)
        _report_settings_errors_for_resource_commands(
            bootstrap_args, resolved_services, stderr
        )
        resource_toggle_result = _run_resource_toggles(
            bootstrap_args, resolved_services, stdout, stderr
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
        with host_lifecycle.output_guard(enabled=_stdout_guard_enabled(bootstrap_args)):
            runtime = _invoke_runtime_builder(
                runtime_builder,
                args=runtime_args,
                cwd=project_root,
                session_dir=session_dir,
                services=resolved_services,
                tool_registry=tool_registry,
                approval_resolver=interactive_approval_resolver,
            )
        with host_lifecycle.output_guard(enabled=_stdout_guard_enabled(runtime_args)):
            list_sessions_result = _run_list_sessions(
                runtime_args, runtime, stdout, stderr
            )
        if list_sessions_result is not None:
            return list_sessions_result

        try:
            with host_lifecycle.output_guard(enabled=_stdout_guard_enabled(bootstrap_args)):
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
    with host_lifecycle.output_guard(enabled=_stdout_guard_enabled(args)):
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

        export_result = _run_export(args, session, stdout, stderr)
        if export_result is not None:
            return export_result

        list_commands_result = _run_list_commands(args, session, stdout, stderr)
        if list_commands_result is not None:
            return list_commands_result

        list_diagnostics_result = _run_list_diagnostics(args, session, stdout, stderr)
        if list_diagnostics_result is not None:
            return list_diagnostics_result

        list_skills_result = _run_list_skills(args, session, stdout, stderr)
        if list_skills_result is not None:
            return list_skills_result

        method_visibility_result = _run_method_visibility(
            args, project_root, stdout, stderr
        )
        if method_visibility_result is not None:
            return method_visibility_result

        list_plugins_result = _run_list_plugins(args, resolved_services, stdout, stderr)
        if list_plugins_result is not None:
            return list_plugins_result

        list_packages_result = _run_list_packages(
            args, session, resolved_services, project_root, stdout, stderr
        )
        if list_packages_result is not None:
            return list_packages_result

        package_lifecycle_result = await _run_package_lifecycle(
            args, session, resolved_services, stdout, stderr
        )
        if package_lifecycle_result is not None:
            return package_lifecycle_result

        command_result = await _run_command(args, session, stdout, stderr)
        if command_result is not None:
            return command_result

        list_models_result = _run_list_models(args, session, stdout, stderr)
        if list_models_result is not None:
            return list_models_result

        effective_tui = _effective_tui(args, stdin=stdin, stdout=stdout)
        work_log_error = _work_log_runtime_error(args, effective_tui=effective_tui)
        if work_log_error is not None:
            stderr.write(f"Error: {work_log_error}.\n")
            return 2
        method_error = _method_runtime_error(args, effective_tui=effective_tui)
        if method_error is not None:
            stderr.write(f"Error: {method_error}.\n")
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
            mode=_observability_mode(args, effective_tui=effective_tui),
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


def _help_belongs_on_stderr(args: CliArgs) -> bool:
    return bool(
        args.prompt is not None
        or args.prompt_steps is not None
        or args.mode in {"print", "json", "rpc", "channel"}
    )


def _stdout_guard_enabled(args: CliArgs) -> bool:
    if (
        args.prompt is not None
        or args.prompt_steps is not None
        or args.mode in {"print", "json", "rpc", "channel"}
    ):
        return True
    return bool(
        (args.list_sessions and args.list_sessions_format == "json")
        or (args.list_models is not False and args.list_models_format == "json")
        or (args.list_commands and args.list_commands_format == "json")
        or (args.list_diagnostics and args.list_diagnostics_format == "json")
        or (args.list_skills and args.list_skills_format == "json")
        or (args.list_methods and args.list_methods_format == "json")
        or (args.show_method is not None and args.show_method_format == "json")
        or (
            args.show_method_plan is not None and args.show_method_plan_format == "json"
        )
        or (args.list_plugins and args.list_plugins_format == "json")
        or (args.list_packages and args.list_packages_format == "json")
        or (args.export is not None and args.export_result_format == "json")
        or (args.command is not None and args.command_result_format == "json")
        or bool(args.materialize_packages)
        or bool(args.update_packages)
        or bool(args.remove_packages)
        or args.update_all_packages
        or args.check_package_updates
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


def _effective_tui(args: CliArgs, *, stdin: TextIO, stdout: TextIO) -> bool:
    if args.tui:
        return True
    if args.no_tui:
        return False
    if not (stream_is_tty(stdin) and stream_is_tty(stdout)):
        return False
    if args.mode != "text":
        return False
    if args.prompt is not None or args.prompt_steps is not None:
        return False
    if args.messages or args.file_args or args.message_prompts:
        return False
    return not _has_command_style_operation(args)


def _work_log_static_error(args: CliArgs) -> str | None:
    if args.work_log is None:
        return None
    if args.tui:
        return "--work-log is not supported in TUI mode"
    if args.mode == "rpc":
        return "--work-log is not supported in RPC mode"
    if args.mode == "channel":
        return "--work-log is not supported in Channel mode"
    if args.prompt_steps is not None:
        return "--work-log is not supported with --prompt-steps"
    return None


def _work_log_runtime_error(args: CliArgs, *, effective_tui: bool) -> str | None:
    if args.work_log is None:
        return None
    if effective_tui:
        return "--work-log is not supported in TUI mode"
    return None


def _method_static_error(args: CliArgs) -> str | None:
    if args.method is not None and args.no_method:
        return "--method cannot be used with --no-method"
    if args.method is None:
        return None
    if args.tui:
        return "--method is not supported in TUI mode"
    if args.mode == "rpc":
        return "--method is not supported in RPC mode"
    if args.mode == "channel":
        return "--method is not supported in Channel mode"
    if args.prompt_steps is not None:
        return "--method is not supported with --prompt-steps"
    return None


def _channel_static_error(args: CliArgs) -> str | None:
    if args.mode != "channel":
        return None
    if args.tui:
        return "--tui is not supported in Channel mode"
    if args.prompt is not None:
        return "--prompt is not supported in Channel mode"
    if args.prompt_steps is not None:
        return "--prompt-steps is not supported in Channel mode"
    if args.messages:
        return "positional messages are not supported in Channel mode"
    if args.file_args:
        return "@file arguments are not supported in Channel mode"
    if args.render_tool_events:
        return "--render-tool-events is not supported in Channel mode"
    return None


def _method_runtime_error(args: CliArgs, *, effective_tui: bool) -> str | None:
    if args.method is None:
        return None
    if effective_tui:
        return "--method is not supported in TUI mode"
    return None


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
        event_log = JsonlEventLogBackend(
            _resolve_work_log_path(args.work_log_inspect, project_root)
        )
        entries = event_log.query(run_id=args.work_log_run)
    except Exception as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    if args.work_log_inspect_format == "json":
        raw_entries = entries[-_WORK_LOG_INSPECT_LIMIT:]
        stdout.write(
            json.dumps(
                [_work_log_entry_summary(entry) for entry in raw_entries],
                ensure_ascii=False,
            )
            + "\n"
        )
    elif args.work_log_inspect_format == "plans-json":
        stdout.write(
            json.dumps(
                [asdict(plan) for plan in project_work_plan_runs(entries)],
                ensure_ascii=False,
            )
            + "\n"
        )
    elif args.work_log_inspect_format == "plans":
        _write_work_log_plan_summary(entries, stdout)
    else:
        _write_work_log_text(entries[-_WORK_LOG_INSPECT_LIMIT:], stdout)
    return 0


def _resolve_work_log_path(raw_path: str, project_root: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def _write_work_log_text(entries: list[Any], stdout: TextIO) -> None:
    stdout.write(
        "\t".join(
            [
                "sequence",
                "kind",
                "run_id",
                "session_id",
                "delivery_hint",
                "method_id",
                "plan_id",
                "step_id",
                "step_index",
                "step_title",
            ]
        )
        + "\n"
    )
    for entry in entries:
        step_index = _work_log_entry_step_index(entry)
        stdout.write(
            "\t".join(
                [
                    str(entry.sequence),
                    _work_log_entry_kind(entry),
                    entry.run_id,
                    entry.session_id,
                    _work_log_entry_delivery_hint(entry),
                    _work_log_entry_method_id(entry),
                    _work_log_entry_plan_id(entry),
                    _work_log_entry_step_id(entry),
                    "" if step_index is None else str(step_index),
                    _work_log_entry_step_title(entry),
                ]
            )
            + "\n"
        )


def _write_work_log_plan_summary(entries: list[Any], stdout: TextIO) -> None:
    stdout.write(
        "\t".join(
            [
                "type",
                "index",
                "id",
                "status",
                "run_id",
                "method_id",
                "completed_steps",
                "failed_steps",
                "current_step",
                "title",
                "deviation",
            ]
        )
        + "\n"
    )
    for plan in project_work_plan_runs(entries):
        stdout.write(
            "\t".join(
                [
                    "plan",
                    "",
                    plan.plan_id,
                    plan.status,
                    "",
                    plan.method_id or "",
                    f"{plan.completed_step_count}/{plan.step_count}",
                    str(plan.failed_step_count),
                    plan.current_step_id or "",
                    "",
                    "",
                ]
            )
            + "\n"
        )
        for fallback_index, step in enumerate(plan.steps, start=1):
            stdout.write(
                "\t".join(
                    [
                        "step",
                        _work_log_plan_step_index(step.metadata, fallback_index),
                        step.step_id,
                        step.status,
                        step.run_id,
                        step.method_id or plan.method_id or "",
                        "",
                        "",
                        "",
                        step.title or "",
                        _work_log_plan_step_deviation_summary(step.deviation),
                    ]
                )
                + "\n"
            )


def _work_log_plan_step_index(
    metadata: Mapping[str, object], fallback_index: int
) -> str:
    step_index = metadata.get("step_index")
    if isinstance(step_index, int) and not isinstance(step_index, bool):
        return str(step_index + 1)
    return str(fallback_index)


def _work_log_plan_step_deviation_summary(deviation: Any) -> str:
    if deviation is None:
        return ""
    deviation_type = getattr(deviation, "deviation_type", "")
    reason = getattr(deviation, "reason", "")
    if deviation_type and reason:
        return f"{deviation_type}: {reason}"
    if deviation_type:
        return str(deviation_type)
    if reason:
        return str(reason)
    return ""


def _work_log_entry_summary(entry: Any) -> dict[str, object]:
    summary: dict[str, object] = {
        "entry_id": entry.entry_id,
        "entry_type": entry.entry_type,
        "sequence": entry.sequence,
        "kind": _work_log_entry_kind(entry),
        "run_id": entry.run_id,
        "session_id": entry.session_id,
        "operation_id": entry.operation_id,
        "event_id": entry.event_id,
        "delivery_hint": _work_log_entry_delivery_hint(entry),
    }
    method_id = _work_log_entry_method_id(entry)
    if method_id:
        summary["method_id"] = method_id
    plan_id = _work_log_entry_plan_id(entry)
    if plan_id:
        summary["plan_id"] = plan_id
    step_id = _work_log_entry_step_id(entry)
    if step_id:
        summary["step_id"] = step_id
    step_index = _work_log_entry_step_index(entry)
    if step_index is not None:
        summary["step_index"] = step_index
    step_title = _work_log_entry_step_title(entry)
    if step_title:
        summary["step_title"] = step_title
    for key in (
        "tool_call_id",
        "tool_name",
        "action_id",
        "policy_disposition",
        "policy_code",
        "policy_reason",
        "approval_required",
        "approval_decision",
        "approval_reason",
        "argument_keys",
        "path",
        "file_path",
        "command",
    ):
        value = _work_log_entry_payload_value(entry, key)
        if isinstance(value, str | bool | int | float | list | tuple):
            summary[key] = value
    return summary


def _work_log_entry_kind(entry: Any) -> str:
    kind = entry.payload.get("kind")
    if isinstance(kind, str) and kind:
        return kind
    return str(entry.entry_type)


def _work_log_entry_delivery_hint(entry: Any) -> str:
    delivery_hint = entry.payload.get("delivery_hint")
    if isinstance(delivery_hint, str):
        return delivery_hint
    return ""


def _work_log_entry_method_id(entry: Any) -> str:
    return _work_log_entry_string_payload_value(entry, "method_id")


def _work_log_entry_plan_id(entry: Any) -> str:
    return _work_log_entry_string_payload_value(entry, "plan_id")


def _work_log_entry_step_id(entry: Any) -> str:
    return _work_log_entry_string_payload_value(entry, "step_id")


def _work_log_entry_step_title(entry: Any) -> str:
    return _work_log_entry_string_payload_value(entry, "step_title")


def _work_log_entry_step_index(entry: Any) -> int | None:
    step_index = _work_log_entry_payload_value(entry, "step_index")
    if isinstance(step_index, int) and not isinstance(step_index, bool):
        return step_index
    return None


def _work_log_entry_string_payload_value(entry: Any, key: str) -> str:
    value = _work_log_entry_payload_value(entry, key)
    if isinstance(value, str):
        return value
    return ""


def _work_log_entry_payload_value(entry: Any, key: str) -> object | None:
    value = entry.payload.get(key)
    if value is not None:
        return value
    nested_payload = entry.payload.get("payload")
    if isinstance(nested_payload, dict):
        return nested_payload.get(key)
    return None


def _has_command_style_operation(args: CliArgs) -> bool:
    return bool(
        args.list_sessions
        or args.source_info
        or args.list_models is not False
        or args.list_commands
        or args.list_diagnostics
        or args.list_skills
        or args.list_methods
        or args.show_method is not None
        or args.show_method_plan is not None
        or args.list_plugins
        or args.list_packages
        or args.export is not None
        or args.diag_export
        or args.command is not None
        or args.enable_skills
        or args.disable_skills
        or args.add_plugin_sources
        or args.remove_plugin_sources
        or args.enable_plugins
        or args.disable_plugins
        or args.install_packages
        or args.uninstall_packages
        or args.materialize_packages
        or args.update_packages
        or args.remove_packages
        or args.update_all_packages
        or args.check_package_updates
        or args.work_log_inspect is not None
    )


def _observability_mode(args: CliArgs, *, effective_tui: bool) -> str:
    if effective_tui:
        return "tui"
    if args.prompt is not None:
        return "prompt"
    if args.prompt_steps is not None:
        return "workflow"
    return args.mode


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


def _run_resource_toggles(
    args: CliArgs,
    services: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not (
        args.enable_skills
        or args.disable_skills
        or args.add_plugin_sources
        or args.remove_plugin_sources
        or args.enable_plugins
        or args.disable_plugins
    ):
        return None
    settings_manager = getattr(services, "settings_manager", None)
    if settings_manager is None:
        stderr.write("Error: settings manager is not available.\n")
        return 1
    try:
        def evaluate_plugin_source(source: str) -> str | None:
            decision = PackageSecurityPolicy().evaluate_package_source(source)
            if decision.disposition == "deny":
                return decision.reason or "Package source denied by policy."
            return None

        result = apply_resource_toggles(
            settings_manager,
            ResourceToggleRequest(
                enable_skills=tuple(args.enable_skills),
                disable_skills=tuple(args.disable_skills),
                add_plugin_sources=tuple(args.add_plugin_sources),
                remove_plugin_sources=tuple(args.remove_plugin_sources),
                enable_plugins=tuple(args.enable_plugins),
                disable_plugins=tuple(args.disable_plugins),
            ),
            evaluate_plugin_source=evaluate_plugin_source,
            is_remote_plugin_source=is_remote_plugin_source,
            on_policy_denied=lambda source, reason: _record_package_policy_diagnostic(
                services, source=source, reason=reason
            ),
        )
    except ResourceToggleError as error:
        for message in error.messages:
            stdout.write(f"{message}\n")
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    except Exception as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    for message in result.messages:
        stdout.write(f"{message}\n")
    return 0


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


def _run_list_sessions(
    args: CliArgs,
    runtime: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.list_sessions:
        return None

    try:
        query = build_session_query(
            cwd=args.session_cwd,
            name=args.session_name_filter,
            parent_session=args.session_parent,
            text=args.session_query,
            has_diagnostics=args.session_has_diagnostics,
            limit=args.session_limit,
        )
        records = list_session_records(
            runtime,
            SessionListingRequest(
                query=query,
                all_sessions=args.all_sessions,
                indexed=args.session_index or args.refresh_session_index,
                refresh_index=args.refresh_session_index,
            ),
            record_projector=_try_normalize_session_record,
        )
    except (SessionListingError, ValueError) as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(format_session_records(records, args.list_sessions_format))
    return 0


def _normalize_session_record(record: Any) -> dict[str, object]:
    """Coding test seam delegating session projection to Harness."""

    return project_session_record(record)


def _try_normalize_session_record(record: Any) -> dict[str, object] | None:
    try:
        return _normalize_session_record(record)
    except Exception:
        return None


def _run_export(
    args: CliArgs,
    session: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if args.export is None:
        return None

    try:
        result = export_session(
            session,
            ExportRequest(format=args.export_format, output=args.export),
        )
    except ExportOperationError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(format_export_result(result, args.export_result_format))
    return 0


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


def _run_list_models(
    args: CliArgs,
    session: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if args.list_models is False:
        return None

    query = ""
    if isinstance(args.list_models, str):
        query = args.list_models.strip().lower()

    try:
        result = list_model_entries(
            session,
            ModelListingRequest(query=query),
        )
    except ModelListingError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    normalized_models = list(result.entries)
    if args.list_models_format == "json":
        stdout.write(json.dumps(normalized_models, ensure_ascii=False) + "\n")
        return 0

    if result.includes_metadata:
        stdout.write(format_model_metadata_table(normalized_models))
        return 0
    for selection in normalized_models:
        stdout.write(f"{selection['provider']}/{selection['model_id']}\n")
    return 0


def _run_list_commands(
    args: CliArgs,
    session: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.list_commands:
        return None

    try:
        records = list_command_records(session)
    except CommandListingError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(format_command_records(records, args.list_commands_format))
    return 0


def _run_list_diagnostics(
    args: CliArgs,
    session: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.list_diagnostics:
        return None
    try:
        normalized = list_diagnostic_records(
            session,
            DiagnosticsListingRequest(limit=args.diagnostics_limit),
        )
    except DiagnosticsListingError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(format_diagnostic_records(normalized, args.list_diagnostics_format))
    return 0


def _run_list_skills(
    args: CliArgs,
    session: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.list_skills:
        return None

    try:
        records = list_skill_records(session)
    except SkillListingError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(format_skill_records(records, args.list_skills_format))
    return 0


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

    try:
        methods = MethodLoader().discover_methods(project_root)
    except Exception as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1

    if args.list_methods:
        normalized = [_normalize_method_entry(method) for method in methods]
        if args.list_methods_format == "json":
            stdout.write(json.dumps(normalized, ensure_ascii=False) + "\n")
            return 0
        for method in normalized:
            stdout.write(
                f"{method['id']}\t{method['name']}\t{method['kind']}\t"
                f"{method['element_type']}\t{method['path']}\n"
            )
        return 0

    if args.show_method_plan is not None:
        method = _find_method(methods, args.show_method_plan)
        if method is None:
            stderr.write(f"Error: method not found: {args.show_method_plan}\n")
            return 1
        try:
            plan = MethodCompiler().compile(
                method, context=MethodContext(domain="coding")
            )
        except Exception as error:
            stderr.write(f"Error: {_format_cli_error(error)}\n")
            return 1
        payload = _normalize_method_plan(method, plan)
        if args.show_method_plan_format == "json":
            stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return 0
        stdout.write(_format_method_plan_detail(payload))
        return 0

    method = _find_method(methods, args.show_method or "")
    if method is None:
        stderr.write(f"Error: method not found: {args.show_method}\n")
        return 1
    payload = _normalize_method_entry(method)
    payload["description"] = _safe_getattr(method, "description", "") or ""
    payload["content"] = _safe_getattr(method, "content", "") or ""
    if args.show_method_format == "json":
        stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return 0
    stdout.write(_format_method_detail(payload))
    return 0


def _find_method(methods: list[Any], id_or_name: str) -> Any | None:
    for method in methods:
        if (
            _safe_getattr(method, "id", None) == id_or_name
            or _safe_getattr(method, "name", None) == id_or_name
        ):
            return method
    return None


def _normalize_method_entry(method: Any) -> dict[str, object]:
    return {
        "id": _safe_getattr(method, "id", "") or "",
        "name": _safe_getattr(method, "name", "") or "",
        "kind": _safe_getattr(method, "kind", "") or "",
        "element_type": _safe_getattr(method, "element_type", None),
        "domain": _safe_getattr(method, "domain", None),
        "meta_role": _safe_getattr(method, "meta_role", None),
        "phase": _safe_getattr(method, "phase", None),
        "path": _safe_getattr(method, "source_path", "") or "",
        "applicability": _normalize_method_applicability(
            _safe_getattr(method, "applicability", None)
        ),
    }


def _normalize_method_applicability(applicability: Any) -> dict[str, object]:
    return {
        "domains": _string_list(_safe_getattr(applicability, "domains", ())),
        "task_types": _string_list(_safe_getattr(applicability, "task_types", ())),
        "contexts": _string_list(_safe_getattr(applicability, "contexts", ())),
        "artifact_types": _string_list(
            _safe_getattr(applicability, "artifact_types", ())
        ),
        "modalities": _string_list(_safe_getattr(applicability, "modalities", ())),
        "toolchains": _string_list(_safe_getattr(applicability, "toolchains", ())),
        "lifecycle": _string_list(_safe_getattr(applicability, "lifecycle", ())),
        "capabilities": _string_list(_safe_getattr(applicability, "capabilities", ())),
        "complexity": _optional_string(
            _safe_getattr(applicability, "complexity", None)
        ),
        "risk": _optional_string(_safe_getattr(applicability, "risk", None)),
        "tags": _normalize_method_tags(_safe_getattr(applicability, "tags", {})),
    }


def _normalize_method_plan(method: Any, plan: Any) -> dict[str, object]:
    return {
        "method": _normalize_method_entry(method),
        "plan": {
            "id": _safe_getattr(plan, "id", "") or "",
            "method_id": _safe_getattr(plan, "method_id", "") or "",
            "mode": _safe_getattr(plan, "mode", "") or "",
            "phase": _safe_getattr(plan, "phase", None),
            "activity": _safe_getattr(plan, "activity", None),
            "task": _safe_getattr(plan, "task", None),
            "metadata": _json_safe(_safe_getattr(plan, "metadata", {})),
            "applicability": _normalize_method_applicability(
                _safe_getattr(plan, "applicability", None)
            ),
        },
        "steps": [
            _normalize_method_plan_step(step)
            for step in _safe_getattr(plan, "steps", ())
        ],
    }


def _normalize_method_plan_step(step: Any) -> dict[str, object]:
    return {
        "id": _safe_getattr(step, "id", "") or "",
        "title": _safe_getattr(step, "title", "") or "",
        "executor": _safe_getattr(step, "executor", "") or "",
        "role_variant": _safe_getattr(step, "role_variant", None),
        "projection": _json_safe(_safe_getattr(step, "projection", {})),
        "constraint": _json_safe(_safe_getattr(step, "constraint", {})),
        "audit": _json_safe(_safe_getattr(step, "audit", {})),
        "applicability": _normalize_method_applicability(
            _safe_getattr(step, "applicability", None)
        ),
    }


def _json_safe(value: Any) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return str(value)


def _normalize_method_tags(tags: Any) -> dict[str, list[str]]:
    if not isinstance(tags, Mapping):
        return {}
    return {
        key: _string_list(value)
        for key, value in sorted(tags.items())
        if isinstance(key, str) and key and _string_list(value)
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _format_method_detail(method: Mapping[str, object]) -> str:
    lines = [
        f"id: {method['id']}",
        f"name: {method['name']}",
        f"kind: {method['kind']}",
    ]
    for key in ("element_type", "domain", "meta_role", "phase", "path", "description"):
        value = method.get(key)
        if value:
            lines.append(f"{key}: {value}")
    applicability_lines = _format_method_applicability_lines(
        method.get("applicability")
    )
    if applicability_lines:
        lines.append("applicability:")
        lines.extend(applicability_lines)
    lines.append("")
    lines.append(str(method.get("content", "")))
    if not lines[-1].endswith("\n"):
        lines[-1] = f"{lines[-1]}\n"
    return "\n".join(lines)


def _format_method_plan_detail(payload: Mapping[str, object]) -> str:
    method = payload.get("method")
    plan = payload.get("plan")
    steps = payload.get("steps")
    method_mapping = method if isinstance(method, Mapping) else {}
    plan_mapping = plan if isinstance(plan, Mapping) else {}
    lines = [
        f"method_id: {method_mapping.get('id', '')}",
        f"method_name: {method_mapping.get('name', '')}",
        f"plan_id: {plan_mapping.get('id', '')}",
        f"mode: {plan_mapping.get('mode', '')}",
        "steps:",
    ]
    if isinstance(steps, list):
        for index, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, Mapping):
                continue
            step_id = raw_step.get("id", "")
            title = raw_step.get("title", "")
            lines.append(f"  {index}. {step_id} - {title}")
            guidance = _method_plan_step_guidance(raw_step)
            if guidance:
                lines.append(f"     guidance: {guidance}")
            constraint = _method_plan_step_mapping(raw_step, "constraint")
            if constraint:
                lines.append(
                    f"     constraint: {json.dumps(constraint, ensure_ascii=False)}"
                )
            audit = _method_plan_step_mapping(raw_step, "audit")
            if audit:
                lines.append(f"     audit: {json.dumps(audit, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines)


def _method_plan_step_guidance(step: Mapping[str, object]) -> str:
    projection = step.get("projection")
    if not isinstance(projection, Mapping):
        return ""
    step_guidance = projection.get("step_guidance")
    if isinstance(step_guidance, str):
        return step_guidance.strip()
    content = projection.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _method_plan_step_mapping(
    step: Mapping[str, object], key: str
) -> Mapping[str, object]:
    value = step.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


def _format_method_applicability_lines(applicability: object) -> list[str]:
    if not isinstance(applicability, Mapping):
        return []
    lines: list[str] = []
    for key in (
        "domains",
        "task_types",
        "contexts",
        "artifact_types",
        "modalities",
        "toolchains",
        "lifecycle",
        "capabilities",
    ):
        values = _string_list(applicability.get(key))
        if values:
            lines.append(f"  {key}: {', '.join(values)}")
    for key in ("complexity", "risk"):
        value = applicability.get(key)
        if isinstance(value, str) and value:
            lines.append(f"  {key}: {value}")
    tags = applicability.get("tags")
    if isinstance(tags, Mapping):
        for key, raw_values in sorted(tags.items()):
            values = _string_list(raw_values)
            if isinstance(key, str) and key and values:
                lines.append(f"  tags.{key}: {', '.join(values)}")
    return lines


def _run_list_plugins(
    args: CliArgs,
    services: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if not args.list_plugins:
        return None

    try:
        normalized = list_plugin_records(
            getattr(services, "settings_manager", None)
        )
    except PluginListingError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    stdout.write(format_plugin_records(normalized, args.list_plugins_format))
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


async def _run_package_lifecycle(
    args: CliArgs, session: Any, services: Any, stdout: TextIO, stderr: TextIO
) -> int | None:
    request = PackageLifecycleRequest(
        install=tuple(args.install_packages),
        materialize=tuple(args.materialize_packages),
        update=tuple(args.update_packages),
        remove=tuple(args.remove_packages),
        uninstall=tuple(args.uninstall_packages),
        check_updates=args.check_package_updates,
        update_all=args.update_all_packages,
        scope=args.package_scope,
    )
    if not request.has_operations:
        return None
    try:
        result = await run_package_lifecycle(
            session,
            request,
            evaluate_install_source=lambda source: _package_source_policy_reason(
                source
            ),
            on_policy_denied=lambda source, reason: _record_package_policy_diagnostic(
                services, source=source, reason=reason
            ),
        )
    except PackageLifecycleError as error:
        for output in error.outputs:
            stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 1
    for output in result.outputs:
        stdout.write(
            json.dumps(output, ensure_ascii=False)
            + "\n"
        )
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


async def _run_command(
    args: CliArgs,
    session: Any,
    stdout: TextIO,
    stderr: TextIO,
) -> int | None:
    if args.command is None:
        return None
    try:
        result = await execute_command(
            session,
            CommandExecutionRequest(
                command=args.command,
                args=args.command_args,
                result_format=args.command_result_format,
            ),
        )
    except CommandExecutionError as error:
        stderr.write(f"Error: {_format_cli_error(error)}\n")
        return 2 if "requires a non-empty" in str(error) else 1
    stdout.write(
        format_command_execution_result(result, result_format=args.command_result_format)
    )
    return 0


def main(argv: list[str] | tuple[str, ...] | None = None) -> int:
    try:
        return asyncio.run(run_cli(sys.argv[1:] if argv is None else argv))
    except KeyboardInterrupt:
        sys.stderr.write("Interrupted.\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
