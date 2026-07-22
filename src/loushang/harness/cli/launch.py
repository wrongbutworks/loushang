"""Product-neutral launch decisions for standard Agent CLI hosts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CliLaunchPlan:
    """Normalized launch intent supplied by a Product argument adapter."""

    mode: str = "text"
    force_tui: bool = False
    disable_tui: bool = False
    prompt_requested: bool = False
    workflow_requested: bool = False
    message_input: bool = False
    file_input: bool = False
    follow_up_input: bool = False
    render_tool_events: bool = False
    work_log_requested: bool = False
    method_requested: bool = False
    method_disabled: bool = False
    session_requested: bool = False
    continue_requested: bool = False
    resume_requested: bool = False
    fork_requested: bool = False
    command_operation: bool = False
    structured_operation_output: bool = False


def cli_help_belongs_on_stderr(plan: CliLaunchPlan) -> bool:
    return bool(
        plan.prompt_requested
        or plan.workflow_requested
        or plan.mode in {"print", "json", "rpc", "channel"}
    )


def cli_output_guard_enabled(plan: CliLaunchPlan) -> bool:
    return cli_help_belongs_on_stderr(plan) or plan.structured_operation_output


def resolve_effective_tui(
    plan: CliLaunchPlan,
    *,
    stdin_is_tty: bool,
    stdout_is_tty: bool,
) -> bool:
    if plan.force_tui:
        return True
    if plan.disable_tui:
        return False
    if not (stdin_is_tty and stdout_is_tty):
        return False
    if plan.mode != "text":
        return False
    if plan.prompt_requested or plan.workflow_requested:
        return False
    if plan.message_input or plan.file_input or plan.follow_up_input:
        return False
    return not plan.command_operation


def cli_static_error(plan: CliLaunchPlan) -> str | None:
    if plan.force_tui and plan.disable_tui:
        return "--tui and --no-tui cannot be used together"
    if plan.fork_requested and not (
        plan.session_requested or plan.continue_requested or plan.resume_requested
    ):
        return "--fork requires --session or --continue / --resume"
    if plan.session_requested and (plan.continue_requested or plan.resume_requested):
        return "--session cannot be used with --continue or --resume"
    if plan.continue_requested and plan.resume_requested:
        return "--continue and --resume cannot be used together"
    if plan.work_log_requested:
        if plan.force_tui:
            return "--work-log is not supported in TUI mode"
        if plan.mode == "rpc":
            return "--work-log is not supported in RPC mode"
        if plan.mode == "channel":
            return "--work-log is not supported in Channel mode"
        if plan.workflow_requested:
            return "--work-log is not supported with --prompt-steps"
    if plan.method_requested and plan.method_disabled:
        return "--method cannot be used with --no-method"
    if plan.method_requested:
        if plan.force_tui:
            return "--method is not supported in TUI mode"
        if plan.mode == "rpc":
            return "--method is not supported in RPC mode"
        if plan.mode == "channel":
            return "--method is not supported in Channel mode"
        if plan.workflow_requested:
            return "--method is not supported with --prompt-steps"
    if plan.mode != "channel":
        return None
    if plan.force_tui:
        return "--tui is not supported in Channel mode"
    if plan.prompt_requested:
        return "--prompt is not supported in Channel mode"
    if plan.workflow_requested:
        return "--prompt-steps is not supported in Channel mode"
    if plan.message_input:
        return "positional messages are not supported in Channel mode"
    if plan.file_input:
        return "@file arguments are not supported in Channel mode"
    if plan.render_tool_events:
        return "--render-tool-events is not supported in Channel mode"
    return None


def cli_runtime_error(
    plan: CliLaunchPlan,
    *,
    effective_tui: bool,
) -> str | None:
    if effective_tui and plan.work_log_requested:
        return "--work-log is not supported in TUI mode"
    if effective_tui and plan.method_requested:
        return "--method is not supported in TUI mode"
    return None


def cli_observability_mode(plan: CliLaunchPlan, *, effective_tui: bool) -> str:
    if effective_tui:
        return "tui"
    if plan.prompt_requested:
        return "prompt"
    if plan.workflow_requested:
        return "workflow"
    return plan.mode


__all__ = [
    "CliLaunchPlan",
    "cli_help_belongs_on_stderr",
    "cli_observability_mode",
    "cli_output_guard_enabled",
    "cli_runtime_error",
    "cli_static_error",
    "resolve_effective_tui",
]
