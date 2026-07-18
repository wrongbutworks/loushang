"""Compatibility aliases for the shared screen conversation state."""

from loushang.harnesstui.conversation.screen_state import (
    ActiveTranscriptWindow,
    ScreenConversationState,
)

ScreenCodingTuiState = ScreenConversationState
ScreenTranscriptWindow = ActiveTranscriptWindow

__all__ = ["ScreenCodingTuiState", "ScreenTranscriptWindow"]
