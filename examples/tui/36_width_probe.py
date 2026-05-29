from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass

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

    normalized = normalize_box_drawing_diagram(DIAGRAM)
    print("")
    print("Normalized diagram lines")
    for line in normalized:
        print(f"{visible_width(line):>3} | {line}")

    print("")
    print("Wrapped diagram")
    for line in DIAGRAM:
        wrapped = wrap_cells(line, width=wrap_width)
        for index, chunk in enumerate(wrapped):
            marker = " " if index == 0 else "+"
            print(f"{marker} {visible_width(chunk):>3} | {strip_control_sequences(chunk)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
