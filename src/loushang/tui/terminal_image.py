from __future__ import annotations

import base64
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.terminal_capabilities import (
    TerminalRuntimeCapabilities,
    detect_terminal_capabilities,
    terminal_environment_from_env,
)

KITTY_IMAGE_PREFIX = "\x1b_G"
ITERM2_IMAGE_PREFIX = "\x1b]1337;File="
ImageProtocol = Literal["kitty", "iterm2"]
ImageProtocolSelection = ImageProtocol | Literal["auto"]
StyleFn = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class CellDimensions:
    width_px: int = 9
    height_px: int = 18


@dataclass(frozen=True, slots=True)
class ImageDimensions:
    width_px: int
    height_px: int


@dataclass(frozen=True, slots=True)
class ImageCellSize:
    columns: int
    rows: int


@dataclass(frozen=True, slots=True)
class TerminalImageRender:
    sequence: str
    rows: int = 1
    protocol: ImageProtocol | None = None
    image_id: int | None = None
    fallback: bool = False

    def lines(self) -> tuple[str, ...]:
        rows = max(1, self.rows)
        if self.fallback or rows == 1:
            return (self.sequence,)
        if self.protocol == "iterm2":
            return (*("" for _ in range(rows - 1)), f"\x1b[{rows - 1}A{self.sequence}")
        return (self.sequence, *("" for _ in range(rows - 1)))


@dataclass(slots=True)
class Image:
    data: bytes
    mime_type: str = ""
    alt_text: str = "image"
    source: str = ""
    protocol: ImageProtocolSelection | None = "auto"
    capabilities: TerminalRuntimeCapabilities | None = None
    dimensions: ImageDimensions | None = None
    max_width_cells: int | None = None
    max_height_cells: int | None = None
    cell_dimensions: CellDimensions = CellDimensions()
    image_id: int | None = None
    fallback_style: StyleFn | None = None
    preserve_aspect_ratio: bool = True
    move_cursor: bool = False

    def render(self, constraints: RenderConstraints) -> RenderResult:
        max_width = self.max_width_cells
        if max_width is None:
            max_width = max(1, min(constraints.width - 2, 60))
        if self.protocol == "auto":
            protocol = _image_protocol_from_capabilities(self.capabilities) if self.capabilities is not None else detect_image_protocol()
        else:
            protocol = self.protocol
        if protocol == "kitty" and self.image_id is None:
            self.image_id = allocate_image_id()
        rendered = render_terminal_image_result(
            alt_text=self.alt_text,
            source=self.source,
            data=self.data,
            mime_type=self.mime_type,
            protocol=protocol,
            capabilities=self.capabilities,
            dimensions=self.dimensions,
            max_width_cells=max_width,
            max_height_cells=self.max_height_cells,
            cell_dimensions=self.cell_dimensions,
            image_id=self.image_id,
            move_cursor=self.move_cursor,
            preserve_aspect_ratio=self.preserve_aspect_ratio,
        )
        if rendered.image_id is not None:
            self.image_id = rendered.image_id
        lines = rendered.lines()
        if rendered.fallback and self.fallback_style is not None:
            lines = tuple(self.fallback_style(line) for line in lines)
        return RenderResult.from_lines([RenderLine(line) for line in lines[: constraints.max_height]], constraints=constraints)


def is_terminal_image_line(line: str) -> bool:
    return KITTY_IMAGE_PREFIX in line or ITERM2_IMAGE_PREFIX in line


def extract_kitty_image_ids(line: str) -> tuple[int, ...]:
    ids: list[int] = []
    seen: set[int] = set()
    offset = 0
    while True:
        start = line.find(KITTY_IMAGE_PREFIX, offset)
        if start < 0:
            break
        params_start = start + len(KITTY_IMAGE_PREFIX)
        params_end = line.find(";", params_start)
        sequence_end = line.find("\x1b\\", params_start)
        if params_end < 0 or (sequence_end >= 0 and sequence_end < params_end):
            offset = params_start
            continue
        for param in line[params_start:params_end].split(","):
            name, separator, value = param.partition("=")
            if name != "i" or not separator:
                continue
            try:
                image_id = int(value)
            except ValueError:
                continue
            if image_id > 0 and image_id not in seen:
                seen.add(image_id)
                ids.append(image_id)
        offset = params_end + 1
    return tuple(ids)


def image_fallback(
    *,
    alt_text: str,
    source: str = "",
    mime_type: str = "",
    dimensions: ImageDimensions | None = None,
) -> str:
    parts: list[str] = []
    if source:
        parts.append(source)
    if mime_type:
        parts.append(f"[{mime_type}]")
    if dimensions is not None:
        parts.append(f"{dimensions.width_px}x{dimensions.height_px}")
    suffix = f" {' '.join(parts)}" if parts else ""
    return f"[image: {alt_text}]{suffix}"


def detect_image_protocol(env: Mapping[str, str] | None = None) -> ImageProtocol | None:
    protocol = detect_terminal_capabilities(terminal_environment_from_env(env)).image_protocol
    return None if protocol == "none" else protocol


def render_terminal_image(
    *,
    alt_text: str,
    source: str = "",
    data: bytes | None = None,
    mime_type: str = "",
    protocol: ImageProtocolSelection | None = "auto",
    env: Mapping[str, str] | None = None,
    capabilities: TerminalRuntimeCapabilities | None = None,
    dimensions: ImageDimensions | None = None,
    max_width_cells: int | None = None,
    max_height_cells: int | None = None,
    cell_dimensions: CellDimensions = CellDimensions(),
    image_id: int | None = None,
    move_cursor: bool = True,
    preserve_aspect_ratio: bool = True,
) -> str:
    return render_terminal_image_result(
        alt_text=alt_text,
        source=source,
        data=data,
        mime_type=mime_type,
        protocol=protocol,
        env=env,
        capabilities=capabilities,
        dimensions=dimensions,
        max_width_cells=max_width_cells,
        max_height_cells=max_height_cells,
        cell_dimensions=cell_dimensions,
        image_id=image_id,
        move_cursor=move_cursor,
        preserve_aspect_ratio=preserve_aspect_ratio,
    ).sequence


def render_terminal_image_result(
    *,
    alt_text: str,
    source: str = "",
    data: bytes | None = None,
    mime_type: str = "",
    protocol: ImageProtocolSelection | None = "auto",
    env: Mapping[str, str] | None = None,
    capabilities: TerminalRuntimeCapabilities | None = None,
    dimensions: ImageDimensions | None = None,
    max_width_cells: int | None = None,
    max_height_cells: int | None = None,
    cell_dimensions: CellDimensions = CellDimensions(),
    image_id: int | None = None,
    move_cursor: bool = True,
    preserve_aspect_ratio: bool = True,
) -> TerminalImageRender:
    if protocol == "auto":
        protocol = _image_protocol_from_capabilities(capabilities) if capabilities is not None else detect_image_protocol(env)
    if dimensions is None and data is not None and mime_type:
        dimensions = get_image_dimensions(data, mime_type)
    if not data or protocol is None:
        return TerminalImageRender(
            image_fallback(alt_text=alt_text, source=source, mime_type=mime_type, dimensions=dimensions),
            fallback=True,
        )
    cell_size = None
    if dimensions is not None and max_width_cells is not None:
        cell_size = calculate_image_cell_size(
            dimensions,
            max_width_cells=max_width_cells,
            max_height_cells=max_height_cells,
            cell_dimensions=cell_dimensions,
        )
    if protocol == "kitty":
        sequence = encode_kitty_image(
            data,
            columns=cell_size.columns if cell_size is not None else None,
            rows=cell_size.rows if cell_size is not None else None,
            image_id=image_id,
            move_cursor=move_cursor,
        )
        sequence = _wrap_for_tmux_if_needed(sequence, capabilities)
        return TerminalImageRender(
            sequence,
            rows=cell_size.rows if cell_size is not None else 1,
            protocol="kitty",
            image_id=image_id,
        )
    sequence = encode_iterm2_image(
        data,
        name=source or alt_text,
        width=cell_size.columns if cell_size is not None else None,
        height="auto" if cell_size is not None else None,
        preserve_aspect_ratio=preserve_aspect_ratio,
    )
    sequence = _wrap_for_tmux_if_needed(sequence, capabilities)
    return TerminalImageRender(
        sequence,
        rows=cell_size.rows if cell_size is not None else 1,
        protocol="iterm2",
        image_id=image_id,
    )


def _image_protocol_from_capabilities(capabilities: TerminalRuntimeCapabilities) -> ImageProtocol | None:
    return None if capabilities.image_protocol == "none" else capabilities.image_protocol


def wrap_tmux_passthrough(sequence: str) -> str:
    if not sequence:
        return sequence
    escaped = sequence.replace("\x1b", "\x1b\x1b")
    return f"\x1bPtmux;{escaped}\x1b\\"


def _wrap_for_tmux_if_needed(sequence: str, capabilities: TerminalRuntimeCapabilities | None) -> str:
    if capabilities is None or not capabilities.tmux_passthrough:
        return sequence
    return wrap_tmux_passthrough(sequence)


def encode_kitty_image(
    data: bytes,
    *,
    columns: int | None = None,
    rows: int | None = None,
    image_id: int | None = None,
    move_cursor: bool = True,
) -> str:
    payload = base64.b64encode(data).decode("ascii")
    params = ["a=T", "f=100", "t=d"]
    if columns is not None:
        params.append(f"c={max(1, int(columns))}")
    if rows is not None:
        params.append(f"r={max(1, int(rows))}")
    if image_id is not None:
        params.append(f"i={max(1, int(image_id))}")
    if not move_cursor:
        params.append("C=1")
    return _encode_kitty_payload(payload, params)


def delete_kitty_image(image_id: int) -> str:
    return f"{KITTY_IMAGE_PREFIX}a=d,d=I,i={max(1, int(image_id))},q=2\x1b\\"


def delete_all_kitty_images() -> str:
    return f"{KITTY_IMAGE_PREFIX}a=d,d=A,q=2\x1b\\"


def hyperlink(text: str, url: str) -> str:
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"


def allocate_image_id() -> int:
    return random.randint(1, 0xFFFFFFFF)


def encode_iterm2_image(
    data: bytes,
    *,
    name: str = "",
    width: int | str | None = None,
    height: int | str | None = None,
    preserve_aspect_ratio: bool = True,
    inline: bool = True,
) -> str:
    payload = base64.b64encode(data).decode("ascii")
    params = [f"inline={1 if inline else 0}"]
    if width is not None:
        params.append(f"width={width}")
    if height is not None:
        params.append(f"height={height}")
    if name:
        encoded_name = base64.b64encode(name.encode("utf-8")).decode("ascii")
        params.append(f"name={encoded_name}")
    if not preserve_aspect_ratio:
        params.append("preserveAspectRatio=0")
    return f"{ITERM2_IMAGE_PREFIX}{';'.join(params)}:{payload}\x07"


def calculate_image_cell_size(
    image_dimensions: ImageDimensions,
    *,
    max_width_cells: int,
    max_height_cells: int | None = None,
    cell_dimensions: CellDimensions = CellDimensions(),
) -> ImageCellSize:
    max_width = max(1, int(max_width_cells))
    max_height = None if max_height_cells is None else max(1, int(max_height_cells))
    image_width = max(1, image_dimensions.width_px)
    image_height = max(1, image_dimensions.height_px)
    cell_width = max(1, cell_dimensions.width_px)
    cell_height = max(1, cell_dimensions.height_px)
    width_scale = (max_width * cell_width) / image_width
    height_scale = width_scale if max_height is None else (max_height * cell_height) / image_height
    scale = min(width_scale, height_scale)
    columns = max(1, min(max_width, _ceil_div(int(image_width * scale), cell_width)))
    rows = _ceil_div(int(image_height * scale), cell_height)
    if max_height is not None:
        rows = min(max_height, rows)
    return ImageCellSize(columns=columns, rows=max(1, rows))


def get_png_dimensions(data: bytes) -> ImageDimensions | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return ImageDimensions(
        width_px=int.from_bytes(data[16:20], "big"),
        height_px=int.from_bytes(data[20:24], "big"),
    )


def get_gif_dimensions(data: bytes) -> ImageDimensions | None:
    if len(data) < 10 or data[:6] not in {b"GIF87a", b"GIF89a"}:
        return None
    return ImageDimensions(
        width_px=int.from_bytes(data[6:8], "little"),
        height_px=int.from_bytes(data[8:10], "little"),
    )


def get_jpeg_dimensions(data: bytes) -> ImageDimensions | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    offset = 2
    while offset < len(data) - 9:
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if 0xC0 <= marker <= 0xC2:
            return ImageDimensions(
                width_px=int.from_bytes(data[offset + 7 : offset + 9], "big"),
                height_px=int.from_bytes(data[offset + 5 : offset + 7], "big"),
            )
        if offset + 4 > len(data):
            return None
        length = int.from_bytes(data[offset + 2 : offset + 4], "big")
        if length < 2:
            return None
        offset += 2 + length
    return None


def get_webp_dimensions(data: bytes) -> ImageDimensions | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8 ":
        if len(data) < 30:
            return None
        return ImageDimensions(
            width_px=int.from_bytes(data[26:28], "little") & 0x3FFF,
            height_px=int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    if chunk == b"VP8L":
        if len(data) < 25:
            return None
        bits = int.from_bytes(data[21:25], "little")
        return ImageDimensions(width_px=(bits & 0x3FFF) + 1, height_px=((bits >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8X":
        return ImageDimensions(
            width_px=int.from_bytes(data[24:27], "little") + 1,
            height_px=int.from_bytes(data[27:30], "little") + 1,
        )
    return None


def get_image_dimensions(data: bytes, mime_type: str) -> ImageDimensions | None:
    normalized = mime_type.lower()
    if normalized == "image/png":
        return get_png_dimensions(data)
    if normalized == "image/jpeg":
        return get_jpeg_dimensions(data)
    if normalized == "image/gif":
        return get_gif_dimensions(data)
    if normalized == "image/webp":
        return get_webp_dimensions(data)
    return None


def _encode_kitty_payload(payload: str, params: list[str]) -> str:
    chunk_size = 4096
    if len(payload) <= chunk_size:
        return f"{KITTY_IMAGE_PREFIX}{','.join(params)};{payload}\x1b\\"
    chunks: list[str] = []
    for index in range(0, len(payload), chunk_size):
        chunk = payload[index : index + chunk_size]
        if index == 0:
            chunks.append(f"{KITTY_IMAGE_PREFIX}{','.join([*params, 'm=1'])};{chunk}\x1b\\")
        elif index + chunk_size >= len(payload):
            chunks.append(f"{KITTY_IMAGE_PREFIX}m=0;{chunk}\x1b\\")
        else:
            chunks.append(f"{KITTY_IMAGE_PREFIX}m=1;{chunk}\x1b\\")
    return "".join(chunks)


def _ceil_div(value: int, divisor: int) -> int:
    return -(-value // divisor)


__all__ = [
    "allocate_image_id",
    "calculate_image_cell_size",
    "CellDimensions",
    "delete_all_kitty_images",
    "delete_kitty_image",
    "detect_image_protocol",
    "ImageProtocol",
    "ImageProtocolSelection",
    "Image",
    "ImageCellSize",
    "ImageDimensions",
    "TerminalImageRender",
    "encode_iterm2_image",
    "encode_kitty_image",
    "extract_kitty_image_ids",
    "get_gif_dimensions",
    "get_image_dimensions",
    "get_jpeg_dimensions",
    "get_png_dimensions",
    "get_webp_dimensions",
    "hyperlink",
    "image_fallback",
    "is_terminal_image_line",
    "render_terminal_image",
    "render_terminal_image_result",
    "wrap_tmux_passthrough",
]
