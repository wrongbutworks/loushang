from __future__ import annotations

import asyncio

import pytest

from loushang.harness.runtime import (
    BoundProductRuntimeContext,
    ProductRuntimeBindings,
    RuntimeBindingState,
    UnboundProductRuntimeContext,
)


def _research_bindings(
    *, cwd: str, active_tools: list[str], calls: list[tuple[str, object]]
) -> ProductRuntimeBindings:
    async def set_active_tools(names: list[str]) -> None:
        calls.append(("tools", names))

    async def set_model(selection: object) -> None:
        calls.append(("model", selection))

    async def compact(instructions: str | None) -> object:
        calls.append(("compact", instructions))
        return {"summary": "research summary"}

    return ProductRuntimeBindings(
        cwd=cwd,
        get_active_tool_names=lambda: list(active_tools),
        get_model_selection=lambda: {"provider": "example", "model": "research"},
        set_active_tools=set_active_tools,
        set_model=set_model,
        request_resource_refresh=lambda: calls.append(("refresh", None)),
        shutdown=lambda: calls.append(("shutdown", None)),
        record_diagnostic=lambda diagnostic: calls.append(
            ("diagnostic", diagnostic)
        ),
        compact=compact,
        get_system_prompt=lambda: "You are a research assistant.",
    )


def test_bound_context_exposes_live_product_capabilities_without_coding() -> None:
    calls: list[tuple[str, object]] = []
    state = RuntimeBindingState(
        _research_bindings(
            cwd="/tmp/research", active_tools=["search"], calls=calls
        )
    )
    context = BoundProductRuntimeContext(
        state.capture(), get_flag_value={"citations": True}.get
    )

    async def scenario() -> None:
        await context.setActiveTools(["search", "read"])
        await context.setModel({"provider": "example", "model": "deep-research"})
        result = await context.compact(
            {"customInstructions": "preserve citations"}
        )
        assert result == {"summary": "research summary"}

    asyncio.run(scenario())

    assert context.cwd == "/tmp/research"
    assert context.getActiveTools() == ["search"]
    assert context.getFlag("citations") is True
    assert context.getSystemPrompt() == "You are a research assistant."
    assert calls == [
        ("tools", ["search", "read"]),
        ("model", {"provider": "example", "model": "deep-research"}),
        ("compact", "preserve citations"),
    ]


def test_bound_context_reads_refreshes_and_honors_invalidation() -> None:
    calls: list[tuple[str, object]] = []
    state = RuntimeBindingState(
        _research_bindings(cwd="/tmp/first", active_tools=["search"], calls=calls),
        stale_message="research session replaced",
    )
    context = BoundProductRuntimeContext(state.capture())

    state.refresh(
        _research_bindings(
            cwd="/tmp/second", active_tools=["search", "read"], calls=calls
        )
    )
    assert context.cwd == "/tmp/second"
    assert context.getActiveTools() == ["search", "read"]

    state.invalidate()
    with pytest.raises(RuntimeError, match="research session replaced"):
        _ = context.cwd


def test_unbound_context_has_conservative_defaults() -> None:
    context = UnboundProductRuntimeContext(
        cwd="/tmp/research",
        get_flag_value={"citations": "required"}.get,
    )

    assert context.cwd == "/tmp/research"
    assert context.get_flag("citations") == "required"
    assert context.get_all_tools() == []
    assert context.has_ui is False
    assert context.setTheme("dark") == {
        "success": False,
        "error": "Theme switching is not supported.",
    }
    with pytest.raises(RuntimeError, match="Extension runtime is not bound"):
        asyncio.run(context.exec_command("pwd"))
