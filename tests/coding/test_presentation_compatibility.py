from __future__ import annotations


def test_coding_rendering_reexports_harness_owned_runtime_contracts() -> None:
    import loushang.coding as coding
    import loushang.coding.tools as coding_tools
    import loushang.coding.tools.rendering as coding_rendering
    import loushang.coding.tools.types as coding_types
    import loushang.harness.presentation as harness_presentation

    owner_symbols = (
        "ToolDefinitionResolver",
        "ToolRenderContext",
        "ToolRenderResultOptions",
        "ToolRenderRuntime",
    )

    for name in owner_symbols:
        assert getattr(coding_tools, name) is getattr(harness_presentation, name)
        assert getattr(coding, name) is getattr(harness_presentation, name)

    assert coding_rendering.ToolDefinitionResolver is harness_presentation.ToolDefinitionResolver
    assert coding_rendering.ToolRenderRuntime is harness_presentation.ToolRenderRuntime
    assert coding_types.ToolRenderContext is harness_presentation.ToolRenderContext
    assert coding_types.ToolRenderResultOptions is harness_presentation.ToolRenderResultOptions


def test_coding_presentation_keeps_product_specific_projection_out_of_harness() -> None:
    import loushang.harness.presentation as harness_presentation
    from loushang.coding.tools import render_tool_result_presentation

    assert not hasattr(harness_presentation, "get_tool_text_output")
    assert not hasattr(harness_presentation, "render_tool_result_presentation")
    assert not hasattr(harness_presentation, "render_tool_result_text")

    rendered = render_tool_result_presentation(
        [{"type": "text", "text": "line\r\n\x1b[31mred\x1b[0m"}],
        {
            "truncation": {"truncated": True, "maxBytes": 1024},
            "fullOutputPath": "/tmp/full.log",
        },
    )

    assert rendered.expanded == "line\nred\n[Truncated: 1.0KB limit]\n[Full output: /tmp/full.log]"
    assert rendered.notices == ("[Truncated: 1.0KB limit]",)
    assert rendered.artifact_paths == ("/tmp/full.log",)


def test_coding_render_runtime_uses_harness_fail_soft_behavior() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.coding.tools import ToolDefinition, ToolRenderRuntime

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[], details={})

    def broken_render_result(result, options, theme, context):
        del result, options, theme, context
        raise RuntimeError("renderer unavailable")

    definition = ToolDefinition(
        name="demo",
        label="Demo",
        description="Demo",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
        render_result=broken_render_result,
    )
    runtime = ToolRenderRuntime()

    assert runtime.render_result(definition, "call-1", AgentToolResult(content=[], details={})) is None
