from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from loushang.harness.presentation import (
    ToolResultPresentation,
    collapse_text,
    normalize_display_text,
    normalize_line_endings,
)

from .protocol import (
    project_tool_details_for_protocol,
    tool_artifact_paths_for_protocol,
)
from .truncate import format_size


def get_tool_text_output(
    content: Sequence[object] | None,
    *,
    show_images: bool = False,
    preserve_ansi: bool = False,
) -> str:
    if not content:
        return ""
    text_blocks: list[str] = []
    image_blocks: list[str] = []
    for part in content:
        part_type = _part_value(part, "type")
        if part_type == "text":
            text = _part_value(part, "text")
            if isinstance(text, str):
                text_blocks.append(normalize_line_endings(text) if preserve_ansi else normalize_display_text(text))
        elif part_type == "image" and not show_images:
            mime_type = _part_value(part, "mime_type") or _part_value(part, "mimeType") or "image/unknown"
            image_blocks.append(f"[Image: {mime_type}]")
    return "\n".join([*text_blocks, *image_blocks])


def render_tool_result_text(
    content: Sequence[object] | None,
    details: object | None = None,
    *,
    show_images: bool = False,
    preserve_ansi: bool = False,
) -> str:
    rendered = render_tool_result_presentation(
        content,
        details,
        show_images=show_images,
        preserve_ansi=preserve_ansi,
    )
    return rendered.expanded


def render_tool_result_presentation(
    content: Sequence[object] | None,
    details: object | None = None,
    *,
    max_collapsed_lines: int = 15,
    show_images: bool = False,
    preserve_ansi: bool = False,
) -> ToolResultPresentation:
    if max_collapsed_lines < 1:
        raise ValueError("max_collapsed_lines must be >= 1")
    body = get_tool_text_output(content, show_images=show_images, preserve_ansi=preserve_ansi)
    notices = tuple(_tool_result_notices(details))
    artifact_paths = tuple(_artifact_paths(details))
    extra_lines = [*notices, *(f"[Full output: {path}]" for path in artifact_paths)]
    expanded = "\n".join(line for line in [body, *extra_lines] if line)
    collapsed, remaining_lines = collapse_text(expanded, max_lines=max_collapsed_lines)
    return ToolResultPresentation(
        expanded=expanded,
        collapsed=collapsed,
        remaining_lines=remaining_lines,
        notices=notices,
        artifact_paths=artifact_paths,
    )


def _tool_result_notices(details: object | None) -> list[str]:
    if not isinstance(details, Mapping):
        return []
    details = project_tool_details_for_protocol(details)
    warnings: list[str] = []
    match_limit = details.get("matchLimitReached")
    if isinstance(match_limit, int):
        warnings.append(f"{match_limit} matches limit")
    result_limit = details.get("resultLimitReached")
    if isinstance(result_limit, int):
        warnings.append(f"{result_limit} results limit")
    entry_limit = details.get("entryLimitReached")
    if isinstance(entry_limit, int):
        warnings.append(f"{entry_limit} entries limit")
    truncation = details.get("truncation")
    max_bytes = _mapping_int(truncation, "maxBytes") or _mapping_int(truncation, "max_bytes") or _mapping_int(details, "max_bytes")
    if _is_truncated(details, truncation) and max_bytes is not None:
        warnings.append(f"{format_size(max_bytes)} limit")
    lines_truncated = bool(details.get("linesTruncated"))
    if lines_truncated:
        warnings.append("some lines truncated")
    return [f"[Truncated: {', '.join(warnings)}]"] if warnings else []


def _artifact_paths(details: object | None) -> list[str]:
    return tool_artifact_paths_for_protocol(details)


def _is_truncated(details: Mapping[str, Any], truncation: object) -> bool:
    if isinstance(truncation, Mapping) and bool(truncation.get("truncated")):
        return True
    return bool(details.get("truncated"))


def _mapping_int(value: object, key: str) -> int | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, int) else None


def _part_value(part: object, key: str) -> object:
    if isinstance(part, dict):
        return part.get(key)
    return getattr(part, key, None)


__all__ = [
    "ToolResultPresentation",
    "get_tool_text_output",
    "normalize_display_text",
    "render_tool_result_presentation",
    "render_tool_result_text",
]
