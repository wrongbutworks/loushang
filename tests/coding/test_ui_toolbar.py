from __future__ import annotations


def test_render_toolbar_omits_empty_fields() -> None:
    from loushang.coding.ui.toolbar import ToolbarSnapshot, render_toolbar

    snapshot = ToolbarSnapshot(
        model="moonshot/kimi-for-coding",
        cwd="/repo",
        branch=None,
        session="254d6156",
        thinking="off",
        running=True,
    )

    assert render_toolbar(snapshot) == (
        "model=moonshot/kimi-for-coding | cwd=/repo | "
        "session=254d6156 | thinking=off | running"
    )


def test_render_toolbar_can_return_single_fixed_width_line() -> None:
    from loushang.coding.ui.toolbar import ToolbarSnapshot, render_toolbar

    snapshot = ToolbarSnapshot(
        model="moonshot/kimi-for-coding",
        cwd="/a/very/long/repository/path",
        thinking="high",
        running=True,
    )

    rendered = render_toolbar(snapshot, width=32)

    assert len(rendered) == 32
    assert rendered.startswith("model=moonshot/")
    assert rendered.endswith("...")
    assert "\x1b[7m" not in rendered
