from __future__ import annotations

import argparse
import os
import re
import select
import shutil
import sys
import time
from dataclasses import dataclass
from typing import TextIO

from loushang.tui import (
    ambiguous_width,
    normalize_box_drawing_diagram,
    set_ambiguous_width,
    strip_control_sequences,
    visible_width,
    wrap_cells,
)


@dataclass(frozen=True, slots=True)
class Sample:
    label: str
    text: str


SAMPLES = (
    Sample("ASCII brackets", "() [] {} <>"),
    Sample("CJK brackets", "（） 【】 《》 「」 『』"),
    Sample("Box drawing", "┌─────────────┐ │ loushang │ └─────────────┘"),
    Sample("Arrows", "◄──────────────────────► ▲ ▼"),
    Sample("Mixed CJK", "产品装配层 (CLI/TUI/Workflow)"),
    Sample("Emoji", "status ✅ ⚡️ 👍🏽 👨\u200d💻"),
)

TERMINAL_SAMPLES = (
    Sample("Keycap", "1️⃣"),
    Sample("Keycap group", "1️⃣ 2️⃣ 3️⃣"),
    Sample("Keycap row", "  │ 组合 │ 1️⃣ 2️⃣ 3️⃣ │"),
    Sample("Bullet", "•"),
    Sample("CJK", "中"),
)

_CURSOR_POSITION_RE = re.compile(rb"\x1b\[(\d+);(\d+)R")
_CLEAR_PROBE_LINE = "\r\x1b[2K"
_CURSOR_POSITION_REQUEST = "\x1b[6n"


DIAGRAM = (
    "  ┌─────────────────────────────────────────────────────────┐",
    "  │  loushang-coding  (产品装配层 - CLI/TUI/Workflow)        │",
    "  │  loushang-channel (边界通信协议层)                        │",
    "  └─────────────────────────────────────────────────────────┘",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe terminal cell-width behavior for TUI rendering.")
    parser.add_argument(
        "--ambiguous-width",
        type=int,
        choices=(1, 2),
        help="Treat East Asian Ambiguous characters as narrow(1) or wide(2).",
    )
    parser.add_argument(
        "--wrap-width",
        type=int,
        default=0,
        help="Width used to show wrap_cells output; defaults to terminal columns minus 1.",
    )
    parser.add_argument(
        "--measure-terminal",
        action="store_true",
        help="Measure real cursor advance with terminal position reports (POSIX TTY only).",
    )
    args = parser.parse_args()

    if args.ambiguous_width is not None:
        set_ambiguous_width(args.ambiguous_width)

    terminal_width = shutil.get_terminal_size((80, 24)).columns
    wrap_width = args.wrap_width or max(1, terminal_width - 1)

    print("Loushang TUI width probe")
    print(f"ambiguous_width={ambiguous_width()}  terminal_columns={terminal_width}  wrap_width={wrap_width}")
    print("")
    print("Character groups")
    print("label                 width  text")
    print("--------------------  -----  ----")
    for sample in SAMPLES:
        print(f"{sample.label:<20}  {visible_width(sample.text):>5}  {sample.text}")

    print("")
    print("Diagram lines")
    for line in DIAGRAM:
        print(f"{visible_width(line):>3} | {line}")

    print("")
    print(f"Wrapped original diagram (max {wrap_width} cells; '+' marks continuation)")
    for line in DIAGRAM:
        wrapped = wrap_cells(line, width=wrap_width)
        for index, chunk in enumerate(wrapped):
            marker = " " if index == 0 else "+"
            print(f"{marker} {visible_width(chunk):>3} | {strip_control_sequences(chunk)}")

    normalized = normalize_box_drawing_diagram(DIAGRAM)
    print("")
    print("Normalized diagram lines (expected aligned)")
    for line in normalized:
        print(f"{visible_width(line):>3} | {line}")

    if args.measure_terminal:
        print("")
        print("Real terminal cursor advance (do not type while probing)")
        for result in _measure_terminal_widths(stdin=sys.stdin, stdout=sys.stdout):
            print(result)
    return 0


def _measure_terminal_widths(
    *,
    stdin: TextIO,
    stdout: TextIO,
    timeout: float = 0.5,
    query_interval: float = 0.25,
) -> tuple[str, ...]:
    if os.name != "posix" or not stdin.isatty() or not stdout.isatty():
        return ("unavailable: requires a POSIX TTY on both stdin and stdout",)

    try:
        import termios
    except ImportError:
        return ("unavailable: termios is unavailable",)

    fd = stdin.fileno()
    try:
        original = termios.tcgetattr(fd)
    except (OSError, ValueError) as error:
        return (f"unavailable: cannot enter terminal probe mode: {error}",)
    probe_attrs = [*original[:6], list(original[6])]
    probe_attrs[3] &= ~(termios.ECHO | termios.ICANON)
    probe_attrs[6][termios.VMIN] = 1
    probe_attrs[6][termios.VTIME] = 0
    results: list[str] = []
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, probe_attrs)
        termios.tcflush(fd, termios.TCIFLUSH)
        origin = _query_cursor_position(fd=fd, stdout=stdout, timeout=timeout)
        if origin is None:
            return ("unavailable: terminal did not answer a CPR cursor query",)

        for sample in TERMINAL_SAMPLES:
            time.sleep(max(0.0, query_interval))
            termios.tcflush(fd, termios.TCIFLUSH)
            end = _query_cursor_position(
                fd=fd,
                stdout=stdout,
                sample=sample.text,
                timeout=timeout,
            )
            if end is None:
                results.append(
                    f"PARTIAL terminal stopped answering cursor queries at {sample.label}"
                )
                break
            results.append(_format_terminal_measurement(sample, origin=origin, end=end))
            if end[0] != origin[0]:
                break
    except (OSError, ValueError) as error:
        results.append(f"PARTIAL terminal query failed: {error}")
    finally:
        try:
            stdout.write(_CLEAR_PROBE_LINE)
            stdout.flush()
            termios.tcflush(fd, termios.TCIFLUSH)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original)

    return tuple(results)


def _query_cursor_position(
    *,
    fd: int,
    stdout: TextIO,
    timeout: float,
    sample: str = "",
) -> tuple[int, int] | None:
    stdout.write(f"{_CLEAR_PROBE_LINE}{sample}{_CURSOR_POSITION_REQUEST}")
    stdout.flush()
    response = bytearray()
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        readable, _, _ = select.select((fd,), (), (), remaining)
        if not readable:
            break
        chunk = os.read(fd, 1024)
        if not chunk:
            break
        response.extend(chunk)
        match = _CURSOR_POSITION_RE.search(response)
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None


def _format_terminal_measurement(
    sample: Sample,
    *,
    origin: tuple[int, int],
    end: tuple[int, int],
) -> str:
    model_width = visible_width(sample.text)
    start_row, start_column = origin
    end_row, end_column = end
    if start_row != end_row or end_column < start_column:
        terminal_width = "-"
        status = "WRAPPED"
    else:
        measured_width = end_column - start_column
        terminal_width = str(measured_width)
        status = "OK" if measured_width == model_width else "MISMATCH"
    codepoints = ",".join(f"U+{ord(char):04X}" for char in sample.text)
    return (
        f"{status} model={model_width} terminal={terminal_width} "
        f"label={sample.label} cps={codepoints} text={sample.text}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
