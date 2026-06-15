from __future__ import annotations

import pytest

from loushang.tui import InputEvent, visible_width
from tests.tui.widget_example_playback import ExampleFrame, play_example


def _assert_frames_fit_viewport(frames: tuple[ExampleFrame, ...], *, width: int, height: int) -> None:
    for frame in frames:
        assert frame.lines
        assert 0 <= frame.cursor[0] < max(height, len(frame.lines))
        assert 0 <= frame.cursor[1] <= width
        for line in frame.lines:
            assert visible_width(line) <= width


@pytest.mark.parametrize(
    ("path", "events", "expected"),
    (
        (
            "examples/tui/52_widgets_tabgroup_searchable_list.py",
            (("type mode", InputEvent(kind="text", text="mode")),),
            ("Search |", "Setting", "Value"),
        ),
        (
            "examples/tui/53_widgets_page_scaffold.py",
            (
                ("up to header", InputEvent(kind="key", key="up")),
                ("right models", InputEvent(kind="key", key="right")),
                ("down body", InputEvent(kind="key", key="down")),
            ),
            ("Body |", "q quit"),
        ),
        (
            "examples/tui/57_widgets_directory_tree.py",
            (
                ("down", InputEvent(kind="key", key="down")),
                ("hidden toggle", InputEvent(kind="text", text="h")),
            ),
            ("Directory Tree", "Hidden files shown", "[q] quit"),
        ),
        (
            "examples/tui/60_widgets_datagrid_large_dataset.py",
            (
                ("tab search", InputEvent(kind="key", key="tab")),
                ("tab sector", InputEvent(kind="key", key="tab")),
                ("type sector", InputEvent(kind="text", text="ai")),
                ("apply", InputEvent(kind="key", key="enter")),
            ),
            ("Min price: [        ]", "Ctrl-B/F", "q quit"),
        ),
    ),
)
@pytest.mark.parametrize(("width", "height"), ((80, 24), (100, 24)))
def test_complex_widget_examples_playback_keep_key_layout_tokens_visible(
    path: str,
    events: tuple[tuple[str, InputEvent], ...],
    expected: tuple[str, ...],
    width: int,
    height: int,
) -> None:
    frames = play_example(path, events=events, width=width, height=height)

    _assert_frames_fit_viewport(frames, width=width, height=height)
    final_text = "\n".join(frames[-1].lines)
    for token in expected:
        assert token in final_text
    assert not any(line.endswith(("Ctrl-", "Min price:", "q q")) for line in frames[-1].lines)


def test_tabgroup_searchable_list_playback_has_single_clean_focus_marker_at_80_columns() -> None:
    frames = play_example(
        "examples/tui/52_widgets_tabgroup_searchable_list.py",
        events=(
            ("up to tabs", InputEvent(kind="key", key="up")),
            ("right models", InputEvent(kind="key", key="right")),
            ("right permissions", InputEvent(kind="key", key="right")),
            ("right activity", InputEvent(kind="key", key="right")),
            ("down nested", InputEvent(kind="key", key="down")),
            ("right nested models", InputEvent(kind="key", key="right")),
        ),
        width=80,
        height=24,
    )

    final = frames[-1].lines
    assert any("*[Activity]" in line for line in final)
    assert any(">[Models]" in line for line in final)
    assert "> [" not in "\n".join(final)
    assert sum(line.count(">") for line in final) == 1


def test_datagrid_large_dataset_playback_keeps_filter_and_footer_readable_at_80_columns() -> None:
    frames = play_example(
        "examples/tui/60_widgets_datagrid_large_dataset.py",
        events=(
            ("tab search", InputEvent(kind="key", key="tab")),
            ("tab sector", InputEvent(kind="key", key="tab")),
            ("type sector", InputEvent(kind="text", text="ai")),
            ("apply", InputEvent(kind="key", key="enter")),
        ),
        width=80,
        height=24,
    )

    final = "\n".join(frames[-1].lines)
    assert "Search: [                ]  Sector: [ai      ]  Matches 334/2,000" in final
    assert "Min price: [        ]" in final
    assert "Status: [" not in final
    assert "PgUp/PgDn | Ctrl-B/F | Home/End | Tab filters | Ctrl-G page | q quit" in final


@pytest.mark.parametrize(
    ("path", "events"),
    (
        (
            "examples/tui/52_widgets_tabgroup_searchable_list.py",
            (("type mode", InputEvent(kind="text", text="mode")),),
        ),
        (
            "examples/tui/53_widgets_page_scaffold.py",
            (
                ("up to header", InputEvent(kind="key", key="up")),
                ("right models", InputEvent(kind="key", key="right")),
                ("down body", InputEvent(kind="key", key="down")),
            ),
        ),
        (
            "examples/tui/57_widgets_directory_tree.py",
            (
                ("down", InputEvent(kind="key", key="down")),
                ("hidden toggle", InputEvent(kind="text", text="h")),
            ),
        ),
        (
            "examples/tui/60_widgets_datagrid_large_dataset.py",
            (
                ("tab search", InputEvent(kind="key", key="tab")),
                ("tab sector", InputEvent(kind="key", key="tab")),
                ("type sector", InputEvent(kind="text", text="ai")),
                ("apply", InputEvent(kind="key", key="enter")),
            ),
        ),
    ),
)
def test_complex_widget_examples_playback_smoke_at_narrow_viewport(
    path: str,
    events: tuple[tuple[str, InputEvent], ...],
) -> None:
    frames = play_example(path, events=events, width=56, height=18)

    _assert_frames_fit_viewport(frames, width=56, height=18)
    assert frames[-1].lines
