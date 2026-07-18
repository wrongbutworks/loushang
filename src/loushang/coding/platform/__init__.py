from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from loushang.coding.platform.changelog import (
    ChangelogEntry,
    find_changelog_path,
    format_changelog_entries,
    parse_changelog,
)
from loushang.coding.platform.clipboard import ClipboardCopyResult, copy_to_clipboard
from loushang.coding.platform.footer_data_provider import (
    FooterDataProvider,
    FooterSnapshot,
    footer_snapshot_to_mapping,
)
from loushang.coding.platform.git import get_git_branch
from loushang.coding.platform.output_guard import (
    flush_raw_stdout,
    is_stdout_taken_over,
    restore_stdout,
    stdout_guard,
    take_over_stdout,
    write_raw_stdout,
)
from loushang.coding.platform.version_check import check_for_new_loushang_version

if TYPE_CHECKING:
    from loushang.tui.clipboard_image import (
        ClipboardImage,
        extension_for_image_mime_type,
        read_clipboard_image,
    )

_LAZY_EXPORTS = {
    "ClipboardImage": ("loushang.tui.clipboard_image", "ClipboardImage"),
    "extension_for_image_mime_type": (
        "loushang.tui.clipboard_image",
        "extension_for_image_mime_type",
    ),
    "read_clipboard_image": (
        "loushang.tui.clipboard_image",
        "read_clipboard_image",
    ),
}


def __getattr__(name: str) -> object:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})


__all__ = [
    "ChangelogEntry",
    "ClipboardCopyResult",
    "ClipboardImage",
    "FooterDataProvider",
    "FooterSnapshot",
    "check_for_new_loushang_version",
    "copy_to_clipboard",
    "extension_for_image_mime_type",
    "find_changelog_path",
    "flush_raw_stdout",
    "format_changelog_entries",
    "footer_snapshot_to_mapping",
    "get_git_branch",
    "is_stdout_taken_over",
    "parse_changelog",
    "read_clipboard_image",
    "restore_stdout",
    "stdout_guard",
    "take_over_stdout",
    "write_raw_stdout",
]
