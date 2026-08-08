"""Compatibility forwarding surface for diagnostic runtime identity."""

from loushang.foundation.observability.runtime_identity import (
    RuntimeIdentityProfile,
    collect_profiled_runtime_identity,
    collect_runtime_identity,
    format_profiled_runtime_identity_text,
    format_runtime_identity_text,
)

__all__ = [
    "RuntimeIdentityProfile",
    "collect_profiled_runtime_identity",
    "collect_runtime_identity",
    "format_profiled_runtime_identity_text",
    "format_runtime_identity_text",
]
