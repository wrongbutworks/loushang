"""Compatibility aliases for the generic TUI clipboard-image capability."""

from loushang.tui.clipboard_image import (
    SUPPORTED_IMAGE_MIME_TYPES as SUPPORTED_IMAGE_MIME_TYPES,
)
from loushang.tui.clipboard_image import ClipboardImage as ClipboardImage
from loushang.tui.clipboard_image import CommandResult as CommandResult
from loushang.tui.clipboard_image import CommandRunner as CommandRunner
from loushang.tui.clipboard_image import NativeClipboardReader as NativeClipboardReader
from loushang.tui.clipboard_image import (
    extension_for_image_mime_type as extension_for_image_mime_type,
)
from loushang.tui.clipboard_image import is_wayland_session as is_wayland_session
from loushang.tui.clipboard_image import read_clipboard_image as read_clipboard_image

__all__ = [
    "ClipboardImage",
    "CommandResult",
    "SUPPORTED_IMAGE_MIME_TYPES",
    "extension_for_image_mime_type",
    "is_wayland_session",
    "read_clipboard_image",
]
