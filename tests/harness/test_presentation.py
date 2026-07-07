from __future__ import annotations


def test_normalize_display_text_strips_ansi_and_normalizes_line_endings() -> None:
    from loushang.harness.presentation import normalize_display_text

    assert normalize_display_text("a\r\n\x1b]0;title\x07\x1b[31mred\x1b[0m") == "a\nred"


def test_collapse_text_reports_remaining_lines() -> None:
    from loushang.harness.presentation import collapse_text

    collapsed, remaining = collapse_text("a\nb\nc", max_lines=2)

    assert collapsed == "a\nb\n... (1 more lines)"
    assert remaining == 1


def test_collapse_text_rejects_non_positive_max_lines() -> None:
    import pytest

    from loushang.harness.presentation import collapse_text

    with pytest.raises(ValueError, match="max_lines must be >= 1"):
        collapse_text("a", max_lines=0)


def test_render_runtime_fails_soft_for_unknown_events_and_missing_renderers() -> None:
    from loushang.harness.presentation import ToolRenderRuntime

    class Definition:
        render_call = None
        render_result = None

    runtime = ToolRenderRuntime()

    assert runtime.render_event({"type": "unknown"}, lambda name: Definition()) is None
    assert runtime.render_event(
        {
            "type": "tool_execution_start",
            "tool_call_id": "call-1",
            "tool_name": "demo",
            "args": {"path": "x"},
        },
        lambda name: Definition(),
    ) is None


def test_render_runtime_preserves_context_state_and_last_rendered() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.harness.presentation import ToolRenderRuntime

    seen: list[tuple[str, object | None, object | None, bool, bool, bool]] = []

    def render_result(result, options, theme, context):
        del result, options, theme
        previous = context.state.get("count", 0)
        context.state["count"] = previous + 1
        rendered = f"{context.tool_call_id}:{previous}:{context.last_rendered}"
        seen.append(
            (
                context.tool_call_id,
                context.args,
                context.last_rendered,
                context.expanded,
                context.is_partial,
                context.show_images,
            )
        )
        return rendered

    class Definition:
        render_call = None

    Definition.render_result = staticmethod(render_result)

    runtime = ToolRenderRuntime(show_images=True)
    result = AgentToolResult(content=[], details={})

    first = runtime.render_event(
        {
            "type": "tool_execution_update",
            "tool_call_id": "call-1",
            "tool_name": "demo",
            "args": {"path": "x"},
            "partial_result": result,
        },
        lambda name: Definition(),
        expanded=True,
    )
    second = runtime.render_event(
        {
            "type": "tool_execution_end",
            "tool_call_id": "call-1",
            "tool_name": "demo",
            "result": result,
        },
        lambda name: Definition(),
    )

    assert first == "call-1:0:None"
    assert second == "call-1:1:call-1:0:None"
    assert seen == [
        ("call-1", {"path": "x"}, None, True, True, True),
        ("call-1", {"path": "x"}, "call-1:0:None", False, False, True),
    ]
