from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, TextIO, cast

from loushang.ai.model import (
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
from loushang.coding.diagnostics.profile import (
    coding_diagnostic_source,
    coding_runtime_identity,
    format_coding_runtime_identity_text,
)
from loushang.coding.domain import (
    CodingDomainApp,
    CodingDomainPreparedTurn,
    CodingDomainRequest,
    MethodPolicy,
)
from loushang.coding.domain.work import create_coding_work_runtime
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
from loushang.coding.tool_pack import register_coding_builtin_tools
from loushang.coding.ui.mode import run_coding_tui
from loushang.coding.workflow import run_prompt_steps_workflow
from loushang.harness.cli import (
    AgentCliLaunchOverlay,
    CliApplicationPorts,
    CliApplicationRuntime,
    CliBootstrapContext,
    CliLaunchPlan,
    CliOperationInsertion,
    CliOperationStage,
    CliParseResult,
    CliPhaseResult,
    CliPreparedTurn,
    CliRuntimeContext,
    CliSessionContext,
    MethodListingError,
    MethodListingRequest,
    agent_cli_bootstrap_args,
    agent_cli_launch_plan,
    agent_image_auto_resize,
    agent_resource_toggle_request,
    agent_session_listing_request,
    agent_session_resolution_request,
    agent_standard_cli_operation_request,
    apply_agent_offline_mode,
    capture_cli_parse,
    cli_help_belongs_on_stderr,
    cli_observability_mode,
    cli_output_guard_enabled,
    cli_runtime_error,
    configure_agent_cli_session,
    configure_agent_resource_loader,
    format_agent_cli_help,
    format_package_records,
    invoke_cli_builder,
    report_agent_resource_settings_errors,
    resolve_agent_session_dir,
    resolve_effective_tui,
    resolve_session,
    run_keyword_cli_turns,
    run_method_listing,
    run_resource_toggle_operation,
    run_session_listing_operation,
    run_standard_cli_operations,
)
from loushang.harness.cli import (
    collect_extension_flags as collect_extension_flags_shared,
)
from loushang.harness.cli import (
    format_cli_error as _format_cli_error,
)
from loushang.harness.config.agent import SettingsManager
from loushang.harness.diagnostics import export_diagnostics_bundle
from loushang.harness.diagnostics.observability_runtime import (
    session_observability_context,
    startup_observability_context,
)
from loushang.harness.extensions.types import ResolvedFlag
from loushang.harness.host.prompt_input import (
    PromptInputPlan,
    resolve_prompt_input,
)
from loushang.harness.resources.plugins import is_remote_plugin_source
from loushang.harness.scenario import run_fake_workflow_cli
from loushang.harness.tools.workspace import workspace_tool_runtime_settings
from loushang.harness.tools.workspace.registry import WorkspaceToolRegistry
from loushang.method import MethodCompiler, MethodContext, MethodLoader
from loushang.work import (
    JsonlEventLogBackend,
    WorkLogInspectionError,
    inspect_work_log,
    resolve_work_log_path,
)
from loushang.work.session import SessionWorkTurn

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
    runtime_settings = workspace_tool_runtime_settings(
        settings_manager,
        policy_factory=PolicyEngine,
    )
    resolved_approval_resolver = (
        approval_resolver
        if approval_resolver is not None
        else runtime_settings.approval_resolver
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
        policy_engine=runtime_settings.policy_engine,
        approval_resolver=resolved_approval_resolver,
    )
    return registry


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
    resource_loader_options = configure_agent_resource_loader(
        services.resource_loader,
        args,
    )
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
    approval_resolver: InteractiveApprovalResolver | None,
):
    return invoke_cli_builder(
        runtime_builder,
        required={
            "args": args,
            "cwd": cwd,
            "session_dir": session_dir,
            "services": services,
            "tool_registry": tool_registry,
        },
        optional={"approval_resolver": approval_resolver},
    )


@dataclass(frozen=True)
class _CodingCliState:
    args: CliArgs
    services: Any
    session_dir: Path
    settings_manager: object | None
    tool_registry: WorkspaceToolRegistry
    approval_resolver: InteractiveApprovalResolver | None


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
    host_lifecycle = ProductHostLifecycle.resolve(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )
    streams = host_lifecycle.streams
    application = CliApplicationRuntime(
        CliApplicationPorts[
            CliArgs,
            _CodingCliState,
            object,
            object,
        ](
            parse_args=_parse_application_args,
            initialize_args=apply_agent_offline_mode,
            launch_plan=_cli_launch_plan,
            args_cwd=lambda args: args.cwd,
            early_operation=lambda context: _run_coding_early_operation(
                context,
                host_lifecycle=host_lifecycle,
                services=services,
                runtime_builder=runtime_builder,
            ),
            validated_operation=lambda context: _run_work_log_inspect(
                context.args,
                context.project_root,
                context.stdout,
                context.stderr,
            ),
            prepare_state=lambda context: _prepare_coding_cli_state(
                context,
                services=services,
                workflow_runner=workflow_runner,
            ),
            startup_context=lambda context, state: (
                startup_observability_context(
                    args=context.args,
                    services=state.services,
                    cwd=context.project_root,
                    source_resolver=coding_diagnostic_source,
                )
            ),
            build_runtime=lambda context, state: _invoke_runtime_builder(
                runtime_builder,
                args=state.args,
                cwd=context.project_root,
                session_dir=state.session_dir,
                services=state.services,
                tool_registry=state.tool_registry,
                approval_resolver=state.approval_resolver,
            ),
            runtime_operation=_run_coding_runtime_operation,
            resolve_session=lambda context: _resolve_session(
                context.state.args,
                context.runtime,
                context.bootstrap.project_root,
            ),
            collect_extension_flags=_collect_extension_flags,
            configure_session=_configure_coding_cli_session,
            session_operations=_run_coding_cli_operations,
            run_host=lambda context: _run_coding_cli_host(
                context,
                host_lifecycle=host_lifecycle,
                mode_runner=mode_runner,
                prompt_runner=prompt_runner,
                workflow_runner=workflow_runner,
                print_runner=print_runner,
                rpc_runner=rpc_runner,
                channel_runner=channel_runner,
                tui_runner=tui_runner,
            ),
            output_guard=lambda enabled: host_lifecycle.output_guard(
                enabled=enabled
            ),
            format_error=_format_cli_error,
        )
    )
    return await application.run(
        tuple(argv or ()),
        stdin=streams.stdin,
        stdout=streams.stdout,
        stderr=streams.stderr,
        cwd=cwd,
    )


def _parse_application_args(
    argv: Sequence[str],
    stderr: TextIO,
    extension_flags: Mapping[str, object] | None,
    allow_unknown: bool,
) -> CliParseResult[CliArgs]:
    return capture_cli_parse(
        parse_args,
        argv,
        stderr,
        cast(
            Mapping[str, ExtensionFlag] | None,
            extension_flags,
        ),
        allow_unknown,
    )


async def _run_coding_early_operation(
    context: CliBootstrapContext[CliArgs],
    *,
    host_lifecycle: ProductHostLifecycle,
    services: BootstrapServices | Any | None,
    runtime_builder: Any,
) -> int | None:
    args = context.args
    if args.help:
        with host_lifecycle.output_guard(
            enabled=cli_output_guard_enabled(context.launch_plan)
        ):
            extension_flags = await _collect_extension_flags_for_help(
                raw_argv=list(context.raw_argv),
                project_root=context.project_root,
                services=services,
                runtime_builder=runtime_builder,
            )
        output = (
            context.stderr
            if cli_help_belongs_on_stderr(context.launch_plan)
            else context.stdout
        )
        output.write(_help_text(extension_flags))
        return 0
    if args.version:
        context.stdout.write(f"{_package_version()}\n")
        return 0
    if args.source_info:
        source_identity = coding_runtime_identity(cwd=context.project_root)
        if args.source_info_format == "json":
            context.stdout.write(
                json.dumps(source_identity, ensure_ascii=False) + "\n"
            )
        else:
            context.stdout.write(
                format_coding_runtime_identity_text(source_identity) + "\n"
            )
        return 0
    return None


async def _prepare_coding_cli_state(
    context: CliBootstrapContext[CliArgs],
    *,
    services: BootstrapServices | Any | None,
    workflow_runner: Any,
) -> CliPhaseResult[_CodingCliState]:
    args = context.args
    resolved_services = services or build_default_services(context.project_root)
    report_agent_resource_settings_errors(
        args,
        getattr(resolved_services, "settings_manager", None),
        stderr=context.stderr,
    )
    resource_toggle_request = agent_resource_toggle_request(args)
    resource_toggle_result = run_resource_toggle_operation(
        getattr(resolved_services, "settings_manager", None),
        resource_toggle_request,
        stdout=context.stdout,
        stderr=context.stderr,
        evaluate_plugin_source=_package_source_policy_reason,
        is_remote_plugin_source=is_remote_plugin_source,
        on_policy_denied=lambda source, reason: _record_package_policy_diagnostic(
            resolved_services, source=source, reason=reason
        ),
        format_error=_format_cli_error,
    )
    if resource_toggle_result is not None:
        return CliPhaseResult.exit(resource_toggle_result)
    runtime_args = agent_cli_bootstrap_args(
        args,
        product_catalog_operation=(
            args.list_methods
            or args.show_method is not None
            or args.show_method_plan is not None
        ),
    )
    session_dir = resolve_agent_session_dir(
        runtime_args,
        project_root=context.project_root,
        settings_manager=resolved_services.settings_manager,
    )
    diag_export_result = _run_diag_export(
        args,
        context.project_root,
        session_dir,
        resolved_services,
        context.stdout,
        context.stderr,
    )
    if diag_export_result is not None:
        return CliPhaseResult.exit(diag_export_result)
    fake_workflow_result = await _run_fake_prompt_steps_workflow_if_requested(
        args,
        project_root=context.project_root,
        workflow_runner=workflow_runner,
        stdout=context.stdout,
        stderr=context.stderr,
    )
    if fake_workflow_result is not None:
        return CliPhaseResult.exit(fake_workflow_result)
    settings_manager = getattr(resolved_services, "settings_manager", None)
    tool_runtime_settings = workspace_tool_runtime_settings(
        settings_manager,
        policy_factory=PolicyEngine,
    )
    configured_resolver = tool_runtime_settings.approval_resolver
    interactive_resolver: InteractiveApprovalResolver | None = None
    approval_resolver: ApprovalResolver
    if configured_resolver is None:
        interactive_resolver = InteractiveApprovalResolver(
            fallback=HeadlessApprovalResolver(mode="deny")
        )
        approval_resolver = interactive_resolver
    else:
        approval_resolver = configured_resolver
    tool_registry = (
        WorkspaceToolRegistry()
        if runtime_args.no_builtin_tools
        else build_builtin_tool_registry(
            diagnostics_service=getattr(
                resolved_services, "diagnostics_service", None
            ),
            settings_manager=settings_manager,
            approval_resolver=approval_resolver,
        )
    )
    return CliPhaseResult.continue_with(
        _CodingCliState(
            args=runtime_args,
            services=resolved_services,
            session_dir=session_dir,
            settings_manager=settings_manager,
            tool_registry=tool_registry,
            approval_resolver=interactive_resolver,
        )
    )


def _run_coding_runtime_operation(
    context: CliRuntimeContext[CliArgs, _CodingCliState, object],
) -> int | None:
    args = context.state.args
    return run_session_listing_operation(
        context.runtime,
        agent_session_listing_request(args),
        stdout=context.bootstrap.stdout,
        stderr=context.bootstrap.stderr,
        format_error=_format_cli_error,
    )


async def _configure_coding_cli_session(
    context: CliSessionContext[CliArgs, _CodingCliState, object, object],
) -> int | None:
    args = context.args
    return await configure_agent_cli_session(
        context.session,
        session_name=args.session_name,
        extension_flag_values=args.extension_flag_values,
        model_selection=None,
        resolve_model_selection=lambda: parse_model_selection_reference(
            args.model,
            provider=args.provider,
        ),
        thinking_level=args.thinking,
        apply_model_selection=lambda session, selection: apply_model_selection(
            session,
            selection,
            settings_manager=context.state.settings_manager,
        ),
        model_result_warning=_model_result_warning,
        stderr=context.bootstrap.stderr,
        format_error=_format_cli_error,
    )


async def _run_coding_cli_operations(
    context: CliSessionContext[CliArgs, _CodingCliState, object, object],
) -> int | None:
    args = context.args
    session = context.session
    bootstrap = context.bootstrap
    return await run_standard_cli_operations(
        session,
        context.state.settings_manager,
        agent_standard_cli_operation_request(args),
        stdout=bootstrap.stdout,
        stderr=bootstrap.stderr,
        insertions=(
            CliOperationInsertion(
                CliOperationStage(
                    "method_visibility",
                    lambda: _run_method_visibility(
                        args,
                        bootstrap.project_root,
                        bootstrap.stdout,
                        bootstrap.stderr,
                    ),
                ),
                target_operation_id="list_skills",
            ),
            CliOperationInsertion(
                CliOperationStage(
                    "list_packages",
                    lambda: _run_list_packages(
                        args,
                        session,
                        context.state.services,
                        bootstrap.project_root,
                        bootstrap.stdout,
                        bootstrap.stderr,
                    ),
                ),
                target_operation_id="list_plugins",
            ),
        ),
        evaluate_install_source=_package_source_policy_reason,
        on_policy_denied=lambda source, reason: _record_package_policy_diagnostic(
            context.state.services, source=source, reason=reason
        ),
        format_error=_format_cli_error,
    )


async def _run_coding_cli_host(
    context: CliSessionContext[CliArgs, _CodingCliState, object, object],
    *,
    host_lifecycle: ProductHostLifecycle,
    mode_runner: Any,
    prompt_runner: Any,
    workflow_runner: Any,
    print_runner: Any,
    rpc_runner: Any,
    channel_runner: Any,
    tui_runner: Any,
) -> int:
    args = context.args
    bootstrap = context.bootstrap
    runtime = context.runtime
    session = context.session
    stdin = bootstrap.stdin
    stdout = bootstrap.stdout
    stderr = bootstrap.stderr
    project_root = bootstrap.project_root
    effective_tui = resolve_effective_tui(
        context.launch_plan,
        stdin_is_tty=stream_is_tty(stdin),
        stdout_is_tty=stream_is_tty(stdout),
    )
    runtime_error = cli_runtime_error(
        context.launch_plan,
        effective_tui=effective_tui,
    )
    if runtime_error is not None:
        stderr.write(f"Error: {runtime_error}.\n")
        return 2
    work_event_log = _resolve_work_event_log(args.work_log, project_root)
    coding_work_runtime = (
        create_coding_work_runtime(
            session=session,
            event_log=work_event_log,
            session_id=lambda: session.session_id,
        )
        if work_event_log is not None
        else None
    )
    with session_observability_context(
        args=args,
        session=session,
        cwd=project_root,
        mode=cli_observability_mode(
            context.launch_plan, effective_tui=effective_tui
        ),
        source_resolver=coding_diagnostic_source,
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
                stderr.write("Error: @file arguments are not supported in RPC mode.\n")
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
                auto_resize_images=agent_image_auto_resize(
                    context.state.settings_manager
                ),
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
                        args, settings_manager=context.state.settings_manager
                    ),
                )
            )
        except ValueError as error:
            stderr.write(f"Error: {_format_method_cli_error(error)}\n")
            return 1
        cli_prepared_turns = _prepared_turns_for_cli(prepared_turns)
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
            return await run_keyword_cli_turns(
                cli_prepared_turns,
                run_turns=host_lifecycle.run_turns,
                runner=prompt_runner,
                input_argument="prompt",
                fixed_arguments={
                    "runtime": runtime,
                    "session": session,
                    "stdout": stdout,
                    "stderr": stderr,
                    "verbose": args.verbose,
                    "work_event_log": work_event_log,
                    "coding_work_runtime": coding_work_runtime,
                },
                images=print_input.images,
                follow_up_messages=print_input.follow_up_messages,
                dispose_candidates=(runtime, session),
            )
        output_mode = "text" if args.mode == "print" else args.mode
        if print_runner is not run_print_mode:
            return await run_keyword_cli_turns(
                cli_prepared_turns,
                run_turns=host_lifecycle.run_turns,
                runner=print_runner,
                input_argument="user_input",
                fixed_arguments={
                    "runtime": runtime,
                    "session": session,
                    "stdout": stdout,
                    "stderr": stderr,
                    "output_mode": output_mode,
                    "render_tool_events": args.render_tool_events,
                    "work_event_log": work_event_log,
                },
                images=print_input.images,
                follow_up_messages=print_input.follow_up_messages,
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
        return await run_keyword_cli_turns(
            cli_prepared_turns,
            run_turns=host_lifecycle.run_turns,
            runner=mode_runner,
            input_argument="user_input",
            fixed_arguments={
                "config": ModeConfig(
                    mode=args.mode,
                    render_tool_events=args.render_tool_events,
                ),
                "runtime": runtime,
                "session": session,
                "stdin": stdin,
                "stdout": stdout,
                "stderr": stderr,
                "work_event_log": work_event_log,
                "coding_work_runtime": coding_work_runtime,
            },
            images=print_input.images,
            follow_up_messages=print_input.follow_up_messages,
            dispose_candidates=(runtime, session),
        )


def _prepared_turn_policy_metadata(
    prepared_turn: Any, key: str
) -> Mapping[str, object] | None:
    value = prepared_turn.metadata.get(key)
    if isinstance(value, Mapping) and value:
        return dict(value)
    return None


def _prepared_turns_for_cli(
    prepared_turns: Sequence[CodingDomainPreparedTurn],
) -> tuple[CliPreparedTurn, ...]:
    return tuple(
        CliPreparedTurn(
            input_text=prepared_turn.prepared_prompt,
            arguments={
                "method_id": prepared_turn.method_id,
                "plan_id": prepared_turn.plan_id,
                "step_id": prepared_turn.step_id,
                "step_index": prepared_turn.step_index,
                "step_title": prepared_turn.step_title,
                "planned_constraint": _prepared_turn_policy_metadata(
                    prepared_turn, "planned_constraint"
                ),
                "audit_policy": _prepared_turn_policy_metadata(
                    prepared_turn, "audit_policy"
                ),
                "plan_facts": _prepared_turn_policy_metadata(
                    prepared_turn, "plan_facts"
                ),
                "step_facts": _prepared_turn_policy_metadata(
                    prepared_turn, "step_facts"
                ),
            },
        )
        for prepared_turn in prepared_turns
    )


def _prepared_turns_to_work_turns(
    prepared_turns: tuple[CodingDomainPreparedTurn, ...],
    *,
    images: Sequence[object] | None,
    follow_up_messages: tuple[str, ...],
) -> tuple[SessionWorkTurn, ...]:
    turns: list[SessionWorkTurn] = []
    for index, prepared_turn in enumerate(prepared_turns):
        turns.append(
            SessionWorkTurn(
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
    product_command_operation = any(
        (
            args.list_methods,
            args.show_method is not None,
            args.show_method_plan is not None,
            args.work_log_inspect is not None,
        )
    )
    product_structured_operation = any(
        (
            args.list_methods and args.list_methods_format == "json",
            args.show_method is not None and args.show_method_format == "json",
            args.show_method_plan is not None
            and args.show_method_plan_format == "json",
        )
    )
    return agent_cli_launch_plan(
        args,
        overlay=AgentCliLaunchOverlay(
            workflow_requested=args.prompt_steps is not None,
            work_log_requested=args.work_log is not None,
            method_requested=args.method is not None,
            method_disabled=args.no_method,
            command_operation=product_command_operation,
            structured_operation_output=product_structured_operation,
        ),
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
    return await run_fake_workflow_cli(
        args.prompt_steps,
        project_root=project_root,
        runner=workflow_runner,
        stdout=stdout,
        stderr=stderr,
        verbose=args.verbose,
        output_mode=_workflow_output_mode(args),
        format_error=_format_cli_error,
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


def _format_method_cli_error(error: ValueError) -> str:
    message = _format_cli_error(error)
    if message.startswith("method not found:"):
        return f"{message}\nRun 'loushang method list' to inspect available methods."
    return message


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
        agent_session_resolution_request(
            args,
            cwd=project_root,
        ),
    )


async def _apply_model_and_thinking_overrides(
    args: CliArgs,
    session: Any,
    stderr: TextIO,
    *,
    settings_manager: object | None = None,
) -> int | None:
    return await configure_agent_cli_session(
        session,
        session_name=None,
        extension_flag_values={},
        model_selection=None,
        resolve_model_selection=lambda: parse_model_selection_reference(
            args.model, provider=args.provider
        ),
        thinking_level=args.thinking,
        apply_model_selection=lambda current, selection: apply_model_selection(
            current,
            selection,
            settings_manager=settings_manager,
        ),
        model_result_warning=_model_result_warning,
        stderr=stderr,
        format_error=_format_cli_error,
    )


def _model_result_warning(result: object) -> str | None:
    warning = persistence_warning_message(result)
    if warning is None:
        return None
    selection = getattr(result, "selection")
    return f"Model changed to {model_selection_ref(selection)}, but {warning}"


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
        session_dir = resolve_agent_session_dir(
            bootstrap_args,
            project_root=project_root,
            settings_manager=resolved_services.settings_manager,
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
    return format_agent_cli_help(
        help_text(),
        extension_flags=cast(Mapping[str, object] | None, extension_flags),
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
