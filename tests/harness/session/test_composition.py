from __future__ import annotations

from dataclasses import fields

from loushang.harness.session.composition import (
    SessionCompositionPorts,
    _resolve_compaction_capability,
)
from loushang.harness.transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
)


def test_compaction_capability_fallback_uses_supported_integer_version() -> None:
    capability = _resolve_compaction_capability(object())

    assert capability.implementation == TURN_AWARE_SUMMARY_IMPLEMENTATION
    assert capability.implementation_version == TURN_AWARE_SUMMARY_VERSION


def test_session_composition_ports_exclude_runtime_owned_forwarders() -> None:
    names = {field.name for field in fields(SessionCompositionPorts)}

    assert names.isdisjoint(
        {
            "exec_service",
            "project_event",
            "refresh_agent_transcript_context",
            "refresh_resources_for_extension_runtime",
            "refresh_resources_for_extension_runtime_async",
            "serialize_context_usage",
        }
    )
