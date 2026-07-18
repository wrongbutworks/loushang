"""Compatibility facade for transcript performance-probe support."""

from loushang.coding.testing.tui.performance import load_session_history_records
from loushang.harnesstui.testing.performance import (
    LongTranscriptRenderMetrics,
    build_synthetic_long_transcript_records,
    characterize_long_transcript_rendering,
)

__all__ = [
    "LongTranscriptRenderMetrics",
    "build_synthetic_long_transcript_records",
    "characterize_long_transcript_rendering",
    "load_session_history_records",
]
