from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

from loushang.harness.config.agent import CompactionSettings
from loushang.harness.session import ProductCompactionExecutor
from loushang.harness.session.composition import (
    ProductCompactionExecutor as CompositionProductCompactionExecutor,
)
from loushang.harness.session.composition import (
    SessionCompositionPorts,
    _compaction_policy,
    _resolve_compaction_capability,
)
from loushang.harness.transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
    TranscriptCompactionPolicy,
)


def test_product_compaction_executor_is_a_public_session_contract() -> None:
    assert ProductCompactionExecutor is CompositionProductCompactionExecutor


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
            "compact_before_prompt",
            "compact_internal",
            "continue_run",
        }
    )


def test_compaction_policy_uses_capability_without_product_override() -> None:
    capability = TranscriptCompactionPolicy(
        enabled=False,
        reserve_tokens=1_234,
        compact_percent=67,
        keep_recent_tokens=456,
    )

    assert _compaction_policy(None, capability) is capability


def test_compaction_policy_uses_capability_with_default_product_settings() -> None:
    capability = TranscriptCompactionPolicy(
        enabled=False,
        reserve_tokens=1_234,
        compact_percent=67,
        keep_recent_tokens=456,
    )

    assert _compaction_policy(CompactionSettings(), capability) == capability


def test_compaction_policy_applies_only_explicit_product_fields() -> None:
    capability = TranscriptCompactionPolicy(
        enabled=True,
        reserve_tokens=1_234,
        compact_percent=67,
        keep_recent_tokens=456,
    )

    assert _compaction_policy(
        CompactionSettings(enabled=False), capability
    ) == TranscriptCompactionPolicy(
        enabled=False,
        reserve_tokens=1_234,
        compact_percent=67,
        keep_recent_tokens=456,
    )


def test_compaction_policy_applies_explicit_product_override() -> None:
    capability = TranscriptCompactionPolicy(
        enabled=False,
        reserve_tokens=1_234,
        compact_percent=67,
        keep_recent_tokens=456,
    )
    override = SimpleNamespace(
        enabled=True,
        reserve_tokens=8_192,
        compact_percent=80,
        keep_recent_tokens=32_768,
    )

    assert _compaction_policy(override, capability) == TranscriptCompactionPolicy(
        enabled=True,
        reserve_tokens=8_192,
        compact_percent=80,
        keep_recent_tokens=32_768,
    )
