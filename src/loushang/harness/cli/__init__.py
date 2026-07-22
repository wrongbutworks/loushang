"""Composable, product-neutral CLI grammar and parsing."""

from loushang.harness.cli.diagnostics_listing import (
    DiagnosticsListingError,
    DiagnosticsListingRequest,
    format_diagnostic_records,
    list_diagnostic_records,
)
from loushang.harness.cli.model_listing import (
    ModelListingError,
    ModelListingRequest,
    ModelListingResult,
    list_model_entries,
)
from loushang.harness.cli.parser import (
    build_parser,
    parse_args,
    register_profile_arguments,
)
from loushang.harness.cli.profile import STANDARD_CLI_PROFILE, CliProfile
from loushang.harness.cli.runtime import (
    CliOperationHandler,
    CliOperationRuntime,
    CliOperationSpec,
    CliOperationUnavailableError,
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
from loushang.harness.cli.types import (
    CliArgumentSpec,
    CliCommandSpec,
    CliInvocation,
    CliProfileError,
    validate_arguments,
)

__all__ = [
    "CliArgumentSpec",
    "CliCommandSpec",
    "CliInvocation",
    "CliOperationHandler",
    "CliOperationRuntime",
    "CliOperationSpec",
    "CliOperationUnavailableError",
    "SessionListingError",
    "SessionListingFormat",
    "SessionListingRequest",
    "build_session_query",
    "format_session_records",
    "list_session_records",
    "SkillListingError",
    "format_skill_records",
    "list_skill_records",
    "ModelListingError",
    "ModelListingRequest",
    "ModelListingResult",
    "list_model_entries",
    "DiagnosticsListingError",
    "DiagnosticsListingRequest",
    "format_diagnostic_records",
    "list_diagnostic_records",
    "CliProfile",
    "CliProfileError",
    "STANDARD_CLI_PROFILE",
    "build_parser",
    "parse_args",
    "register_profile_arguments",
    "validate_arguments",
]
