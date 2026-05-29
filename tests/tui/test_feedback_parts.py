from __future__ import annotations

from typing import Any

from loushang.tui import InputEvent, RenderConstraints, visible_width


def rendered_text(part: Any, *, width: int = 20, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(line.text for line in result.lines)


def test_rule_renders_dynamic_border_to_autowrap_safe_width() -> None:
    from loushang.tui import DynamicBorder, Rule

    assert rendered_text(Rule(), width=5, height=1) == ("────",)
    assert rendered_text(DynamicBorder(), width=3, height=1) == ("──",)


def test_width_filling_feedback_parts_reserve_last_terminal_cell() -> None:
    from loushang.tui import Loader, Rule, WorkedDivider

    assert visible_width(rendered_text(Rule(), width=5, height=1)[0]) == 4
    assert visible_width(rendered_text(Loader(message="Loading", frames=(), leading_spacer=False), width=12, height=1)[0]) == 11
    assert visible_width(rendered_text(WorkedDivider(3.01), width=24, height=1)[0]) == 23


def test_rule_renders_label_and_preserves_autowrap_safe_width() -> None:
    from loushang.tui import Rule

    line = rendered_text(Rule(label="Worked for 3.01s"), width=28, height=1)[0]

    assert line == "─ Worked for 3.01s ────────"
    assert visible_width(line) == 27


def test_rule_applies_style_without_affecting_visible_width() -> None:
    from loushang.tui import Rule, strip_control_sequences

    line = rendered_text(Rule(style=lambda text: f"\x1b[2m{text}\x1b[0m"), width=8, height=1)[0]

    assert strip_control_sequences(line) == "───────"
    assert visible_width(line) == 7


def test_loader_renders_leading_spacer_frame_message_and_truncates() -> None:
    from loushang.tui import Loader

    now = [0]
    loader = Loader(message="Working on files", frames=("a", "b"), interval_ms=100, now_ms=lambda: now[0])

    assert rendered_text(loader, width=14, height=3) == ("", " a Workin\x1b[0m...\x1b[0m ")

    now[0] = 100
    assert rendered_text(loader, width=14, height=3) == ("", " b Workin\x1b[0m...\x1b[0m ")


def test_loader_supports_empty_indicator_stop_and_message_updates() -> None:
    from loushang.tui import Loader

    now = [0]
    loader = Loader(message="Loading", frames=(), now_ms=lambda: now[0])

    assert rendered_text(loader, width=12, height=2) == ("", " Loading   ")

    loader.set_message("Done")
    loader.stop()
    now[0] = 10_000

    assert rendered_text(loader, width=12, height=2) == ("", " Done      ")


def test_loader_reports_next_animation_frame_due_and_disables_when_stopped() -> None:
    from loushang.tui import Loader

    now = [1_000]
    loader = Loader(message="Loading", frames=("a", "b"), interval_ms=80, now_ms=lambda: now[0])

    assert loader.next_frame_due_ms(after_ms=1_000) == 1_080
    assert loader.next_frame_due_ms(after_ms=1_079) == 1_080
    assert loader.next_frame_due_ms(after_ms=1_080) == 1_160

    loader.stop()

    assert loader.next_frame_due_ms(after_ms=1_160) is None

    loader.set_indicator(frames=("x",))
    assert loader.next_frame_due_ms(after_ms=1_160) is None


def test_cancellable_loader_aborts_once_on_escape_and_disposes() -> None:
    from loushang.tui import CancellableLoader

    calls: list[str] = []
    loader = CancellableLoader(message="Loading", frames=(">",), on_abort=lambda: calls.append("abort"))

    intent = loader.handle_input(InputEvent(kind="key", key="esc"))
    loader.handle_input(InputEvent(kind="key", key="esc"))

    assert loader.aborted is True
    assert calls == ["abort"]
    assert intent is not None
    assert intent.kind == "abort"

    loader.dispose()
    assert loader.running is False


def test_worked_divider_uses_rule_shape_and_elapsed_format() -> None:
    from loushang.tui import WorkedDivider

    assert rendered_text(WorkedDivider(elapsed_seconds=95.4), width=30, height=1) == (
        "─ Worked for 1m 35.40s ──────",
    )
