from __future__ import annotations

from loushang.coding.ui.transcript_reader import (
    TranscriptReaderSurface as CodingTranscriptReaderSurface,
)
from loushang.harnesstui.conversation.reader import TranscriptReaderSurface


def test_coding_transcript_reader_is_harnesstui_compatibility_alias() -> None:
    assert CodingTranscriptReaderSurface is TranscriptReaderSurface
