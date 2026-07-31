from __future__ import annotations

from loushang.harness.session.composition import _resolve_compaction_capability
from loushang.harness.transcript import (
    TURN_AWARE_SUMMARY_IMPLEMENTATION,
    TURN_AWARE_SUMMARY_VERSION,
)


def test_compaction_capability_fallback_uses_supported_integer_version() -> None:
    capability = _resolve_compaction_capability(object())

    assert capability.implementation == TURN_AWARE_SUMMARY_IMPLEMENTATION
    assert capability.implementation_version == TURN_AWARE_SUMMARY_VERSION
