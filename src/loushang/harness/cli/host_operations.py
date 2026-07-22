"""Reusable CLI host operations over injected Product capabilities."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TextIO

from loushang.harness.agent_transcript.catalog import try_project_session_record
from loushang.harness.cli.command_execution import (
    CommandExecutionError,
    CommandExecutionRequest,
    execute_command,
    format_command_execution_result,
)
from loushang.harness.cli.command_listing import (
    CommandListingError,
    format_command_records,
    list_command_records,
)
from loushang.harness.cli.diagnostics_listing import (
    DiagnosticsListingError,
    DiagnosticsListingRequest,
    format_diagnostic_records,
    list_diagnostic_records,
)
from loushang.harness.cli.export import (
    ExportOperationError,
    ExportRequest,
    ExportResultFormat,
    export_session,
    format_export_result,
)
from loushang.harness.cli.model_listing import (
    ModelListingError,
    ModelListingRequest,
    list_model_entries,
)
from loushang.harness.cli.package_lifecycle import (
    PackageLifecycleError,
    PackageLifecycleRequest,
    run_package_lifecycle,
)
from loushang.harness.cli.plugin_listing import (
    PluginListingError,
    format_plugin_records,
    list_plugin_records,
)
from loushang.harness.cli.resource_toggles import (
    ResourceToggleError,
    ResourceToggleRequest,
    apply_resource_toggles,
)
from loushang.harness.cli.session_listing import (
    SessionListingError,
    SessionListingFormat,
    SessionListingRequest,
    build_session_query,
    format_session_records,
    list_session_records,
)
from loushang.harness.cli.skill_listing import (
    SkillListingError,
    format_skill_records,
    list_skill_records,
)
from loushang.harness.session.model_selection import format_model_metadata_table

CliErrorFormatter = Callable[[BaseException], str]
PolicyEvaluator = Callable[[str], str | None]
PolicyDeniedHandler = Callable[[str, str | None], None]
RemoteSourcePredicate = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class SessionListingOperationRequest:
    """CLI-facing session query fields resolved inside the operation boundary."""

    output_format: SessionListingFormat = "tsv"
    cwd: str | None = None
    name: str | None = None
    parent_session: str | None = None
    text: str | None = None
    has_diagnostics: bool | None = None
    limit: int | None = None
    all_sessions: bool = False
    indexed: bool = False
    refresh_index: bool = False


def run_session_listing_operation(
    runtime: object,
    request: SessionListingOperationRequest | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None:
        return None
    try:
        query = build_session_query(
            cwd=request.cwd,
            name=request.name,
            parent_session=request.parent_session,
            text=request.text,
            has_diagnostics=request.has_diagnostics,
            limit=request.limit,
        )
        records = list_session_records(
            runtime,
            SessionListingRequest(
                query=query,
                all_sessions=request.all_sessions,
                indexed=request.indexed,
                refresh_index=request.refresh_index,
            ),
            record_projector=try_project_session_record,
        )
    except (SessionListingError, ValueError) as error:
        return _write_error(stderr, error, format_error=format_error)
    stdout.write(format_session_records(records, request.output_format))
    return 0


def run_export_operation(
    session: object,
    request: ExportRequest | None,
    *,
    result_format: ExportResultFormat,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None:
        return None
    try:
        result = export_session(session, request)
    except ExportOperationError as error:
        return _write_error(stderr, error, format_error=format_error)
    stdout.write(format_export_result(result, result_format))
    return 0


def run_model_listing_operation(
    session: object,
    request: ModelListingRequest | None,
    *,
    output_format: str,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None:
        return None
    try:
        result = list_model_entries(session, request)
    except ModelListingError as error:
        return _write_error(stderr, error, format_error=format_error)
    entries = list(result.entries)
    if output_format == "json":
        stdout.write(json.dumps(entries, ensure_ascii=False) + "\n")
    elif result.includes_metadata:
        stdout.write(format_model_metadata_table(entries))
    else:
        for selection in entries:
            stdout.write(f"{selection['provider']}/{selection['model_id']}\n")
    return 0


def run_command_listing_operation(
    session: object,
    output_format: str | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if output_format is None:
        return None
    try:
        records = list_command_records(session)
    except CommandListingError as error:
        return _write_error(stderr, error, format_error=format_error)
    stdout.write(format_command_records(records, output_format))
    return 0


def run_diagnostics_listing_operation(
    session: object,
    request: DiagnosticsListingRequest | None,
    *,
    output_format: str,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None:
        return None
    try:
        records = list_diagnostic_records(session, request)
    except DiagnosticsListingError as error:
        return _write_error(stderr, error, format_error=format_error)
    stdout.write(format_diagnostic_records(records, output_format))
    return 0


def run_skill_listing_operation(
    session: object,
    output_format: str | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if output_format is None:
        return None
    try:
        records = list_skill_records(session)
    except SkillListingError as error:
        return _write_error(stderr, error, format_error=format_error)
    stdout.write(format_skill_records(records, output_format))
    return 0


def run_plugin_listing_operation(
    settings_manager: object | None,
    output_format: str | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if output_format is None:
        return None
    try:
        records = list_plugin_records(settings_manager)
    except PluginListingError as error:
        return _write_error(stderr, error, format_error=format_error)
    stdout.write(format_plugin_records(records, output_format))
    return 0


def run_resource_toggle_operation(
    settings_manager: object | None,
    request: ResourceToggleRequest | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    evaluate_plugin_source: PolicyEvaluator | None = None,
    is_remote_plugin_source: RemoteSourcePredicate | None = None,
    on_policy_denied: PolicyDeniedHandler | None = None,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None or not request.has_operations:
        return None
    if settings_manager is None:
        stderr.write("Error: settings manager is not available.\n")
        return 1
    try:
        result = apply_resource_toggles(
            settings_manager,
            request,
            evaluate_plugin_source=evaluate_plugin_source,
            is_remote_plugin_source=is_remote_plugin_source,
            on_policy_denied=on_policy_denied,
        )
    except ResourceToggleError as error:
        for message in error.messages:
            stdout.write(f"{message}\n")
        return _write_error(stderr, error, format_error=format_error)
    except Exception as error:
        return _write_error(stderr, error, format_error=format_error)
    for message in result.messages:
        stdout.write(f"{message}\n")
    return 0


async def run_package_lifecycle_operation(
    session: object,
    request: PackageLifecycleRequest | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    evaluate_install_source: PolicyEvaluator | None = None,
    on_policy_denied: PolicyDeniedHandler | None = None,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None or not request.has_operations:
        return None
    try:
        result = await run_package_lifecycle(
            session,
            request,
            evaluate_install_source=evaluate_install_source,
            on_policy_denied=on_policy_denied,
        )
    except PackageLifecycleError as error:
        _write_json_records(stdout, error.outputs)
        return _write_error(stderr, error, format_error=format_error)
    _write_json_records(stdout, result.outputs)
    return 0


async def run_command_operation(
    session: object,
    request: CommandExecutionRequest | None,
    *,
    stdout: TextIO,
    stderr: TextIO,
    format_error: CliErrorFormatter = str,
) -> int | None:
    if request is None:
        return None
    try:
        result = await execute_command(session, request)
    except CommandExecutionError as error:
        exit_code = 2 if "requires a non-empty" in str(error) else 1
        return _write_error(
            stderr,
            error,
            format_error=format_error,
            exit_code=exit_code,
        )
    stdout.write(
        format_command_execution_result(result, result_format=request.result_format)
    )
    return 0


def _write_error(
    stderr: TextIO,
    error: BaseException,
    *,
    format_error: CliErrorFormatter,
    exit_code: int = 1,
) -> int:
    stderr.write(f"Error: {format_error(error)}\n")
    return exit_code


def _write_json_records(
    stdout: TextIO,
    records: tuple[Mapping[str, object], ...],
) -> None:
    for record in records:
        stdout.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__ = [
    "CliErrorFormatter",
    "SessionListingOperationRequest",
    "run_command_listing_operation",
    "run_command_operation",
    "run_diagnostics_listing_operation",
    "run_export_operation",
    "run_model_listing_operation",
    "run_package_lifecycle_operation",
    "run_plugin_listing_operation",
    "run_resource_toggle_operation",
    "run_session_listing_operation",
    "run_skill_listing_operation",
]
