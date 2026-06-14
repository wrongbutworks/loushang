from __future__ import annotations

import runpy

from loushang.tui import InputEvent, RenderConstraints, strip_control_sequences
from tests.tui.widget_example_playback import play_example

EXAMPLE_PATH = "examples/tui/54_widgets_settings_page_assembly.py"


def test_settings_page_assembly_example_imports_and_renders_default_config_page() -> None:
    namespace = runpy.run_path(EXAMPLE_PATH, run_name="__test__")
    app = namespace["build_app"]()
    result = app.render(RenderConstraints(width=100, max_height=26))
    lines = tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)

    assert lines[0].startswith("Settings")
    assert "*[Config]" in lines[1]
    assert "[Status]" in lines[1]
    assert "[Model]" in lines[1]
    assert "╭" in lines[4]
    assert "Search settings..." in lines[5]
    assert any("Setting" in line and "Value" in line for line in lines)
    assert any("Current model" in line and "Use Model tab" in line for line in lines)
    assert any("more below" in line.lower() for line in lines)
    assert lines[-1].startswith("Search |")


def test_settings_page_assembly_focus_path_between_search_list_and_tabs() -> None:
    frames = play_example(
        EXAMPLE_PATH,
        events=(
            ("down list", InputEvent(kind="key", key="down")),
            ("up search", InputEvent(kind="key", key="up")),
            ("up tabs", InputEvent(kind="key", key="up")),
            ("down search", InputEvent(kind="key", key="down")),
        ),
        width=100,
        height=26,
    )

    assert any(line.startswith("> Current model") for line in frames[1].lines)
    assert frames[2].lines[-1].startswith("Search |")
    assert ">[Config]" in frames[3].lines[1]
    assert "*[Config]" in frames[4].lines[1]
    assert frames[4].lines[-1].startswith("Search |")


def test_settings_page_assembly_toggles_config_setting_without_focus_jump() -> None:
    frames = play_example(
        EXAMPLE_PATH,
        events=(
            ("type compact", InputEvent(kind="text", text="compact")),
            ("down list", InputEvent(kind="key", key="down")),
            ("space toggle", InputEvent(kind="key", key="space")),
        ),
        width=100,
        height=26,
    )

    final = frames[-1].lines
    assert any(line.startswith("> Auto-compact") and "true" in line for line in final)
    assert any("Toggled: Auto-compact -> true" in line for line in final)
    assert final[-1].startswith("Settings |")


def test_settings_page_assembly_switches_to_model_searchable_list() -> None:
    frames = play_example(
        EXAMPLE_PATH,
        events=(
            ("up tabs", InputEvent(kind="key", key="up")),
            ("right model", InputEvent(kind="key", key="right")),
            ("down body", InputEvent(kind="key", key="down")),
            ("type coding", InputEvent(kind="text", text="coding")),
        ),
        width=100,
        height=26,
    )

    final = frames[-1].lines
    assert "*[Model]" in final[1]
    assert "coding" in "\n".join(final)
    assert any("kimi-for-coding" in line for line in final)
    assert final[-1].startswith("Search |")


def test_settings_page_assembly_renders_nested_stats_tabs_with_single_header_focus_marker() -> None:
    frames = play_example(
        EXAMPLE_PATH,
        events=(
            ("up tabs", InputEvent(kind="key", key="up")),
            ("right model", InputEvent(kind="key", key="right")),
            ("right usage", InputEvent(kind="key", key="right")),
            ("right stats", InputEvent(kind="key", key="right")),
            ("down stats", InputEvent(kind="key", key="down")),
            ("up nested tabs", InputEvent(kind="key", key="up")),
            ("right nested models", InputEvent(kind="key", key="right")),
        ),
        width=100,
        height=26,
    )

    final = frames[-1].lines
    assert "*[Stats]" in final[1]
    assert any("Overview" in line and ">[Models]" in line for line in final)
    assert any("Model usage" in line or "kimi-for-coding" in line for line in final)
    assert sum(line.count(">") for line in final) == 1
