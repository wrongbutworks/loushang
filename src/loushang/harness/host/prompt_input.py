"""Product-neutral prompt input assembly for Agent-facing hosts.

This module owns the reusable ``stdin``/``@file``/image input mechanics.  A
Product supplies its argument grammar and can keep its own prompt wording;
the input protocol and image payload construction remain shared.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from loushang.ai.types import ImagePart
from loushang.harness.tools.workspace.path_utils import resolve_tool_path
from loushang.harness.tools.workspace.read import (
    PillowReadImageResizer,
    detect_image_dimensions,
    format_image_dimension_note,
    image_exceeds_inline_limits,
)


@dataclass(frozen=True)
class PromptInputPlan:
    """Prompt text, initial images, and messages for the next turn."""

    user_input: str | None
    images: list[ImagePart] | None
    follow_up_messages: tuple[str, ...]


def resolve_prompt_input(
    *,
    prompt: str | None,
    messages: tuple[str, ...],
    message_prompts: tuple[str, ...],
    file_args: tuple[str, ...],
    stdin: TextIO,
    cwd: Path,
    auto_resize_images: bool = True,
) -> PromptInputPlan:
    """Assemble one prompt from injected streams and file arguments."""

    file_text, images = _process_file_args(
        file_args,
        cwd,
        auto_resize_images=auto_resize_images,
    )
    parts: list[str] = []
    stdin_content = _read_stdin_prompt(stdin)
    if stdin_content is not None:
        parts.append(stdin_content)
    if file_text:
        parts.append(file_text)
    if prompt is not None:
        parts.append(prompt.strip())
    if messages:
        parts.append(" ".join(messages).strip())

    user_input = "".join(parts).strip() or None
    follow_up_messages = message_prompts
    if user_input is None and follow_up_messages:
        user_input = follow_up_messages[0]
        follow_up_messages = follow_up_messages[1:]
    return PromptInputPlan(
        user_input=user_input,
        images=images or None,
        follow_up_messages=follow_up_messages,
    )


def _process_file_args(
    file_args: tuple[str, ...],
    cwd: Path,
    *,
    auto_resize_images: bool = True,
) -> tuple[str, list[ImagePart]]:
    text_parts: list[str] = []
    images: list[ImagePart] = []
    for file_arg in file_args:
        path = resolve_tool_path(file_arg, cwd=str(cwd))
        payload = path.read_bytes()
        if not payload:
            continue
        mime_type = _detect_supported_image_mime_type(path, payload)
        if mime_type is not None:
            original_dimensions = detect_image_dimensions(mime_type, payload)
            dimensions = original_dimensions
            encoded = base64.b64encode(payload)
            dimension_note: str | None = None
            if auto_resize_images and image_exceeds_inline_limits(encoded, dimensions):
                resize_result = PillowReadImageResizer().resize_image(
                    payload,
                    mime_type=mime_type,
                    dimensions=dimensions,
                )
                if resize_result is None:
                    text_parts.append(
                        f'<file name="{path}">'
                        "[Image omitted: could not be resized below the inline image size limit.]"
                        "</file>\n"
                    )
                    continue
                payload = resize_result.payload
                mime_type = resize_result.mime_type
                dimensions = resize_result.dimensions or detect_image_dimensions(
                    mime_type, payload
                )
                original_dimensions = (
                    resize_result.original_dimensions or original_dimensions
                )
                encoded = base64.b64encode(payload)
                dimension_note = format_image_dimension_note(
                    original_dimensions=original_dimensions,
                    dimensions=dimensions,
                    was_resized=resize_result.was_resized,
                )
            images.append(
                ImagePart(
                    type="image",
                    data=encoded.decode("ascii"),
                    mime_type=mime_type,
                )
            )
            text_parts.append(f'<file name="{path}">{dimension_note or ""}</file>\n')
            continue
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise RuntimeError(f"Could not read file {path}: {error}") from error
        text_parts.append(f'<file name="{path}">\n{content}\n</file>\n')
    return "".join(text_parts), images


def _detect_supported_image_mime_type(path: Path, payload: bytes) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"} and payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if suffix == ".png" and payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if suffix == ".gif" and (
        payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a")
    ):
        return "image/gif"
    if (
        suffix == ".webp"
        and len(payload) >= 12
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
    ):
        return "image/webp"
    return None


def _read_stdin_prompt(stdin: TextIO) -> str | None:
    isatty = getattr(stdin, "isatty", None)
    if callable(isatty):
        try:
            if isatty():
                return None
        except OSError:
            pass
    content = stdin.read()
    if not isinstance(content, str):
        return None
    stripped = content.strip()
    return stripped or None


__all__ = ["PromptInputPlan", "resolve_prompt_input"]
