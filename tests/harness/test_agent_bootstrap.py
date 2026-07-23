from __future__ import annotations

from loushang.harness.bootstrap import BootstrapActivationRuntime
from loushang.harness.config.agent import ControlConfig
from loushang.harness.session.bootstrap import (
    AgentBootstrapRequest,
    AgentBootstrapRuntime,
    AgentSessionConstructionRequest,
    AgentSessionConstructionRuntime,
    StandardAgentSessionActivationEffects,
    activate_standard_agent_session_configuration,
    standard_agent_session_activation_plan,
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


def test_standard_agent_session_activation_plan_preserves_capability_order() -> None:
    calls: list[str] = []

    def effect(name: str):
        return lambda _selection, _context: calls.append(name)

    runtime = BootstrapActivationRuntime(
        standard_agent_session_activation_plan(
            StandardAgentSessionActivationEffects(
                startup_checks=effect("startup_checks"),
                package_sources=effect("package_sources"),
                resource_roots=effect("resource_roots"),
                resources=effect("resources"),
                extensions=effect("extensions"),
                cwd_audit=effect("cwd_audit"),
                model_registry=effect("model_registry"),
            )
        )
    )

    result = runtime.activate(ControlConfig(), object())

    assert result.report.ok
    assert calls == [
        "startup_checks",
        "package_sources",
        "resource_roots",
        "resources",
        "extensions",
        "cwd_audit",
        "model_registry",
    ]


def test_standard_agent_session_activation_propagates_first_failure() -> None:
    def effect(name: str):
        def apply(_selection, _context):
            if name == "resources":
                raise RuntimeError("resource failure")

        return apply

    effects = StandardAgentSessionActivationEffects(
        startup_checks=effect("startup_checks"),
        package_sources=effect("package_sources"),
        resource_roots=effect("resource_roots"),
        resources=effect("resources"),
        extensions=effect("extensions"),
        cwd_audit=effect("cwd_audit"),
        model_registry=effect("model_registry"),
    )

    try:
        activate_standard_agent_session_configuration(
            ControlConfig(),
            object(),
            effects=effects,
        )
    except RuntimeError as error:
        assert str(error) == "resource failure"
    else:
        raise AssertionError("activation failure was not propagated")
