from __future__ import annotations

from loushang.harness.session.bootstrap import (
    AgentBootstrapRequest,
    AgentBootstrapRuntime,
    AgentSessionConstructionRequest,
    AgentSessionConstructionRuntime,
)


def test_agent_bootstrap_runtime_builds_agent_and_product_session() -> None:
    calls: list[tuple[str, object]] = []

    class FakeAgent:
        session_id = None

    def agent_factory(**kwargs):
        calls.append(("agent", kwargs))
        return FakeAgent()

    request = AgentBootstrapRequest(
        session_id="session-1",
        system_prompt="prompt",
        thinking_level="off",
        model=None,
        convert_to_llm=lambda value: value,
        steering_mode="one-at-a-time",
        follow_up_mode="one-at-a-time",
        thinking_budgets={"high": 100},
        max_retry_delay_ms=50,
    )

    result = AgentBootstrapRuntime[FakeAgent, str]().construct(
        request,
        agent_factory=agent_factory,
        session_factory=lambda agent: f"session:{agent.session_id}",
    )

    assert result == "session:session-1"
    assert calls[0][1]["initial_state"] == {
        "system_prompt": "prompt",
        "thinking_level": "off",
        "tools": [],
    }
    assert calls[0][1]["max_retry_delay_ms"] == 50


def test_agent_session_construction_runtime_uses_product_callbacks() -> None:
    class FakeAgent:
        session_id = None

    diagnostics: list[object] = []
    request = AgentSessionConstructionRequest(
        session_id="session-2",
        base_prompt="base",
        resolved_prompt="resolved",
        thinking_level="off",
        model=None,
        convert_to_llm=lambda value: value,
        steering_mode="one-at-a-time",
        follow_up_mode="one-at-a-time",
        thinking_budgets={},
        max_retry_delay_ms=None,
        stream_fn=None,
        resource_bundle={"resources": []},
        tools=None,
        tool_registry=None,
        allowed_tool_names=None,
        active_tool_names=None,
        no_tools_mode=None,
    )

    result = AgentSessionConstructionRuntime[FakeAgent, str, dict, object]().construct(
        request,
        agent_factory=lambda **kwargs: FakeAgent(),
        register_extension_tools=lambda bundle, registry: (
            bundle,
            registry,
            ["extension-diagnostic"],
        ),
        record_extension_diagnostics=diagnostics.extend,
        session_factory=lambda agent, bundle, registry, active, prompt, mode: (
            agent.session_id,
            bundle,
            active,
            prompt,
            mode,
        ),
    )

    assert result == ("session-2", {"resources": []}, None, "base", None)
    assert diagnostics == ["extension-diagnostic"]
