from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import time
from dataclasses import dataclass
from typing import TextIO

from loushang.tui import (
    Box,
    CancellableLoader,
    Container,
    DynamicBorder,
    InputEvent,
    InputReader,
    Loader,
    RenderConstraints,
    RenderLine,
    RenderLoop,
    RenderResult,
    Rule,
    Spacer,
    TerminalSize,
    Text,
    ThemeResolver,
    TruncatedText,
    TuiRuntime,
    WorkedDivider,
    apply_theme_style,
    strip_control_sequences,
    truncate_to_width,
    visible_width,
)
from loushang.tui.terminal import ProcessTerminalPort
from loushang.tui.terminal_input import (
    TerminalInputMode,
    read_input_chunk_or_render_tick,
)


@dataclass(frozen=True, slots=True)
class ShowcaseItem:
    name: str
    summary: str
    sample: str


ITEMS = (
    ShowcaseItem("Text", "wrapped text, padding, ANSI preservation", "text"),
    ShowcaseItem("Box", "child composition with padding and background", "box"),
    ShowcaseItem("Spacer", "fixed empty rows inside a container", "spacer"),
    ShowcaseItem("TruncatedText", "single-line truncation by terminal cells", "truncated"),
    ShowcaseItem("Rule", "terminal-width divider with an optional label", "rule"),
    ShowcaseItem("DynamicBorder", "border primitive used by frame chrome", "dynamic_border"),
    ShowcaseItem("Loader", "animated indicator and message truncation", "loader"),
    ShowcaseItem("CancellableLoader", "abort-aware loader UI Part", "cancellable_loader"),
    ShowcaseItem("WorkedDivider", "completed-run divider shape", "worked_divider"),
    ShowcaseItem("Theme + ANSI", "theme tokens, resets, and nested ANSI", "theme"),
    ShowcaseItem("Width / Unicode", "CJK, emoji, combining marks, OSC-safe width", "width"),
)


THEME = ThemeResolver(
    defaults={
        "showcase.header": {"bold": True, "color": "bright_cyan"},
        "showcase.muted": {"color": 250},
        "showcase.accent": {"color": "cyan", "bold": True},
        "showcase.selected": {"color": "black", "background": "bright_cyan", "bold": True},
        "showcase.panel": {"color": 252, "background": 236},
        "showcase.rule": {"color": 245},
        "showcase.loader.indicator": {"color": "yellow"},
        "showcase.loader.message": {"color": "bright_white"},
        "showcase.worked": {"dim": True},
        "showcase.success": {"color": "green"},
    }
)


class BasicShowcaseApp:
    def __init__(self) -> None:
        self.selected = 0
        self.activated = 0
        self.loader = Loader(
            message="Animating through the runtime scheduler",
            now_ms=_monotonic_ms,
            leading_spacer=False,
            theme=THEME,
            indicator_theme_token="showcase.loader.indicator",
            message_theme_token="showcase.loader.message",
        )
        self.cancellable_loader = CancellableLoader(
            message="Abort-aware loader; Enter marks it as handled",
            frames=("◐", "◓", "◑", "◒"),
            interval_ms=120,
            now_ms=_monotonic_ms,
            leading_spacer=False,
            theme=THEME,
            indicator_theme_token="showcase.loader.indicator",
            message_theme_token="showcase.loader.message",
        )

    @property
    def current_item(self) -> ShowcaseItem:
        return ITEMS[self.selected]

    def move(self, delta: int) -> None:
        self.selected = (self.selected + delta) % len(ITEMS)

    def activate(self) -> None:
        self.activated = self.selected
        if self.current_item.sample == "cancellable_loader":
            if self.cancellable_loader.aborted:
                self.cancellable_loader.aborted = False
                self.cancellable_loader.start()
            else:
                self.cancellable_loader.abort()

    def handle_event(self, event: InputEvent) -> bool:
        if event.kind == "key":
            if event.key == "up":
                self.move(-1)
                return True
            if event.key == "down":
                self.move(1)
                return True
            if event.key == "enter":
                self.activate()
                return True
            return False
        if event.kind != "text":
            return False
        handled = False
        for char in event.text:
            if char in {"k", "K"}:
                self.move(-1)
                handled = True
            elif char in {"j", "J"}:
                self.move(1)
                handled = True
            elif char in {"\t", " "}:
                self.activate()
                handled = True
        return handled

    def next_frame_due_ms(self, *, after_ms: int) -> int | None:
        if self.current_item.sample == "loader":
            return self.loader.next_frame_due_ms(after_ms=after_ms)
        if self.current_item.sample == "cancellable_loader":
            return self.cancellable_loader.next_frame_due_ms(after_ms=after_ms)
        return None

    def render(self, constraints: RenderConstraints) -> RenderResult:
        width = constraints.width
        height = constraints.visible_height or constraints.max_height
        header = _fit(
            apply_theme_style("Loushang TUI Basic Showcase", THEME.resolve("showcase.header"))
            + apply_theme_style("  ↑/↓ or k/j select · enter activate · q quit", THEME.resolve("showcase.muted")),
            width,
        )
        body_height = max(1, min(constraints.max_height - 1, height - 1))
        if width < 48:
            rows = [header, *self._render_compact(width, body_height)]
            return RenderResult.from_lines([RenderLine(row) for row in rows], constraints=constraints)

        left_width = _left_width(width)
        right_width = width - left_width - 3
        list_lines = self._render_list(left_width, body_height)
        detail_lines = self._render_detail(right_width, body_height)
        rows: list[str] = [header]
        for index in range(body_height):
            left = list_lines[index] if index < len(list_lines) else ""
            right = detail_lines[index] if index < len(detail_lines) else ""
            rows.append(f"{_fit(left, left_width)} │ {_fit(right, right_width)}")
        return RenderResult.from_lines([RenderLine(row) for row in rows], constraints=constraints)

    def _render_compact(self, width: int, height: int) -> list[str]:
        item = self.current_item
        rows = [
            _fit(f"› {item.name}", width),
            _fit(item.summary, width),
            _fit(Rule(theme=THEME, theme_token="showcase.rule").render(_rc(width, 1)).lines[0].text, width),
            *_sample_lines(item.sample, width, max(1, height - 4), self),
            _fit(f"{self.selected + 1}/{len(ITEMS)}", width),
        ]
        return [_fit(row, width) for row in rows[:height]]

    def _render_list(self, width: int, height: int) -> list[str]:
        title = apply_theme_style("Basic UI Parts", THEME.resolve("showcase.accent"))
        rows = [_fit(title, width), _fit(Rule(theme=THEME, theme_token="showcase.rule").render(_rc(width, 1)).lines[0].text, width)]
        for index, item in enumerate(ITEMS):
            prefix = "› " if index == self.selected else "  "
            label = truncate_to_width(prefix + item.name, max_width=width, ellipsis="...", pad=True)
            if index == self.selected:
                label = apply_theme_style(strip_control_sequences(label), THEME.resolve("showcase.selected"))
            rows.append(_fit(label, width))
        rows.append("")
        rows.append(apply_theme_style("Enter toggles selected demo.", THEME.resolve("showcase.muted")))
        return rows[:height]

    def _render_detail(self, width: int, height: int) -> list[str]:
        item = self.current_item
        rows = [
            apply_theme_style(item.name, THEME.resolve("showcase.header")),
            apply_theme_style(item.summary, THEME.resolve("showcase.muted")),
            "",
        ]
        rows.extend(_sample_lines(item.sample, width, max(1, height - len(rows)), self))
        rows.append("")
        rows.append(
            apply_theme_style(
                f"Selected {self.selected + 1}/{len(ITEMS)} · activated {ITEMS[self.activated].name}",
                THEME.resolve("showcase.muted"),
            )
        )
        return [_fit(row, width) for row in rows[:height]]


def _sample_lines(sample: str, width: int, height: int, app: BasicShowcaseApp) -> list[str]:
    constraints = _rc(width, height)
    if sample == "text":
        text = Text(
            "Plain text wraps by cell width. ANSI stays intact: \x1b[31mred\x1b[0m, CJK=中文, emoji=🙂.",
            padding_x=1,
            padding_y=1,
            theme=THEME,
            theme_token="showcase.panel",
        )
        return _part_lines(text, constraints)
    if sample == "box":
        box = Box(padding_x=2, padding_y=1, theme=THEME, theme_token="showcase.panel")
        box.add_child(Text("Box composes child renderables.", padding_x=0, padding_y=0))
        box.add_child(Text("Theme background fills the full line.", padding_x=0, padding_y=0))
        return _part_lines(box, constraints)
    if sample == "spacer":
        container = Container(
            [
                Text("Before spacer", padding_x=0, padding_y=0),
                Spacer(2),
                Text("After two spacer rows", padding_x=0, padding_y=0),
            ]
        )
        return _part_lines(container, constraints)
    if sample == "truncated":
        return _part_lines(
            TruncatedText(
                "This line is deliberately long: 中文 width and emoji 🙂 are measured before ellipsis.",
                padding_x=1,
                padding_y=1,
                theme=THEME,
                theme_token="showcase.panel",
            ),
            constraints,
        )
    if sample == "rule":
        return [
            *_part_lines(Rule(label="Plain rule", theme=THEME, theme_token="showcase.rule"), _rc(width, 1)),
            *_part_lines(Rule(label="Short", character="-"), _rc(width, 1)),
        ]
    if sample == "dynamic_border":
        return [
            *_part_lines(DynamicBorder(theme=THEME, theme_token="showcase.rule"), _rc(width, 1)),
            _fit("DynamicBorder tracks terminal width every render.", width),
            *_part_lines(DynamicBorder(theme=THEME, theme_token="showcase.rule"), _rc(width, 1)),
        ]
    if sample == "loader":
        return _part_lines(app.loader, constraints)
    if sample == "cancellable_loader":
        state = "aborted" if app.cancellable_loader.aborted else "running"
        status = apply_theme_style(f"state={state}", THEME.resolve("showcase.success"))
        return [*_part_lines(app.cancellable_loader, constraints), status]
    if sample == "worked_divider":
        return _part_lines(WorkedDivider(125.42, theme=THEME, theme_token="showcase.worked"), _rc(width, 1))
    if sample == "theme":
        styled = apply_theme_style(
            "Outer theme survives \x1b[31minner red\x1b[0m reset and resumes.",
            {"background": "blue", "color": "bright_white"},
        )
        return _part_lines(Text(styled, padding_x=1, padding_y=1), constraints)
    if sample == "width":
        examples = [
            "ASCII abc width=3",
            "CJK 中文 width=4",
            "Emoji 🙂 width depends on terminal policy",
            "Combining e\u0301 is one visual cluster",
        ]
        return [_fit(f"{line} · measured={visible_width(line)}", width) for line in examples]
    return ["No sample."]


def _part_lines(part: object, constraints: RenderConstraints) -> list[str]:
    render = getattr(part, "render")
    result = render(constraints)
    return [line.text for line in result.lines]


def _rc(width: int, height: int) -> RenderConstraints:
    return RenderConstraints(width=max(1, width), max_height=max(1, height), visible_height=max(1, height))


def _left_width(total_width: int) -> int:
    return min(max(20, total_width // 3), total_width - 13)


def _fit(text: str, width: int) -> str:
    return truncate_to_width(text, max_width=width, ellipsis="...", pad=True)


def _terminal_size() -> TerminalSize:
    size = shutil.get_terminal_size((100, 28))
    return TerminalSize(columns=size.columns, rows=size.lines)


def _monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


async def run_interactive(*, stdin: TextIO, stdout: TextIO) -> int:
    app = BasicShowcaseApp()
    reader = InputReader()
    runtime = TuiRuntime(
        render_loop=RenderLoop(app),
        terminal=ProcessTerminalPort(output=stdout, size_provider=_terminal_size, track_screen=False),
    )
    stdout.write("\n")
    stdout.flush()
    with TerminalInputMode(stdin=stdin, stdout=stdout):
        runtime.render_now()
        while True:
            data = await read_input_chunk_or_render_tick(stdin, runtime=runtime, active_task=None)
            if data is None:
                continue
            if data == "":
                runtime.render_now()
                return 0
            exit_requested = False
            changed = False
            for event in reader.feed(data):
                if _is_exit_event(event):
                    exit_requested = True
                    break
                changed = app.handle_event(event) or changed
            if changed:
                runtime.render_now()
            if exit_requested:
                runtime.render_now()
                stdout.write("\n")
                stdout.flush()
                return 0


def _is_exit_event(event: InputEvent) -> bool:
    if event.kind == "key" and event.key == "ctrl_c":
        return True
    return event.kind == "text" and any(char in {"q", "Q"} for char in event.text)


def print_snapshot(*, stdout: TextIO, width: int, height: int) -> None:
    app = BasicShowcaseApp()
    result = app.render(RenderConstraints(width=width, max_height=height, visible_height=height))
    for line in result.lines:
        stdout.write(line.text + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive showcase for loushang.tui basic UI Parts.")
    parser.add_argument("--snapshot", action="store_true", help="print one static render instead of entering raw mode")
    parser.add_argument("--width", type=int, default=100, help="snapshot width")
    parser.add_argument("--height", type=int, default=24, help="snapshot height")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.snapshot:
        print_snapshot(stdout=sys.stdout, width=args.width, height=args.height)
        return 0
    return asyncio.run(run_interactive(stdin=sys.stdin, stdout=sys.stdout))


if __name__ == "__main__":
    raise SystemExit(main())
