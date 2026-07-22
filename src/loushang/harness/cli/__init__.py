"""Composable, product-neutral CLI grammar and parsing."""

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
    "CliProfile",
    "CliProfileError",
    "STANDARD_CLI_PROFILE",
    "build_parser",
    "parse_args",
    "register_profile_arguments",
    "validate_arguments",
]
