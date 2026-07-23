from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import loushang.harness.session.bootstrap as bootstrap_module
from loushang.harness.bootstrap import BootstrapActivationRuntime
from loushang.harness.config.agent import ControlConfig
from loushang.harness.session.bootstrap import (
    AgentBootstrapRequest,
    AgentBootstrapRuntime,
    AgentProductConstructionPorts,
    AgentProductConstructionRequest,
    AgentProductConstructionRuntime,
    AgentSessionConstructionRequest,
    AgentSessionConstructionRuntime,
    StandardAgentSessionActivationEffects,
    StandardAgentSessionConfigurationResult,
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


def test_agent_product_construction_runtime_composes_existing_owners(
    monkeypatch,
) -> None:
    actions: list[tuple[object, ...]] = []
    settings = SimpleNamespace(
        system_prompt="configured",
        default_model=None,
        steering_mode="one-at-a-time",
        follow_up_mode="all",
        thinking_budgets={},
        retry=SimpleNamespace(provider_max_retry_delay_ms=25),
        enabled_models=("research/*",),
    )
    diagnostics = SimpleNamespace(
        record_resource_diagnostics=lambda values, **kwargs: actions.append(
            ("diagnostics", tuple(values), kwargs)
        )
    )
    extension_runtime = object()
    configuration = cast(
        Any,
        SimpleNamespace(
            settings=settings,
            session_id="research-session",
            resource_loader=object(),
            model_registry=SimpleNamespace(
                build_model=lambda selection: selection,
                ai_registry=SimpleNamespace(get_endpoint=lambda _selection: None),
                get_model=lambda pattern: f"model:{pattern}",
            ),
            diagnostics_service=diagnostics,
        ),
    )
    monkeypatch.setattr(
        bootstrap_module.StandardAgentSessionConfigurationRuntime,
        "configure",
        lambda _self, _request: StandardAgentSessionConfigurationResult(
            resource_bundle={"resources": []},
            extension_runtime=extension_runtime,
            cwd_bound_services_audit=cast(Any, "audit"),
        ),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "resolve_base_system_prompt",
        lambda **_kwargs: "base prompt",
    )
    monkeypatch.setattr(
        bootstrap_module,
        "assemble_prompt",
        lambda **_kwargs: SimpleNamespace(system_prompt="assembled prompt"),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "resolve_session_model",
        lambda *_args, **_kwargs: "resolved-model",
    )
    monkeypatch.setattr(
        bootstrap_module,
        "register_resource_extension_tools",
        lambda **kwargs: (
            kwargs["resource_bundle"],
            kwargs["tool_registry"],
            ("extension-diagnostic",),
        ),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "scoped_models_from_patterns",
        lambda patterns, **_kwargs: tuple(patterns),
    )

    class FakeAgent:
        session_id = None

    disposed: list[bool] = []
    result = AgentProductConstructionRuntime[
        FakeAgent,
        tuple[object, ...],
        dict[str, object],
        object,
        object,
    ]().construct(
        AgentProductConstructionRequest(
            configuration=configuration,
            ports=AgentProductConstructionPorts(
                activate_resources=lambda bundle: bundle,
                prompt_section_composer=object(),
                tool_pack_composer=object(),
                list_tool_definitions=lambda _runtime: (),
                get_tool_source_info=lambda _runtime, _name: None,
                dispose_capabilities=lambda: disposed.append(True),
            ),
            default_system_prompt="research default",
            explicit_system_prompt=None,
            append_system_prompt=(),
            model=None,
            thinking_level="off",
            tools=None,
            tool_registry=None,
            allowed_tool_names=None,
            active_tool_names=None,
            no_tools=None,
            stream_fn=None,
            convert_to_llm=lambda value: value,
            agent_factory=lambda **kwargs: (
                actions.append(("agent", kwargs)) or FakeAgent()
            ),
            session_factory=lambda agent, bundle, extensions, registry, active, prompt, mode: (
                agent.session_id,
                bundle,
                extensions,
                registry,
                active,
                prompt,
                mode,
            ),
            on_default_model_unavailable=lambda *_args: None,
            set_scoped_models=lambda session, models: actions.append(
                ("scoped-models", session, tuple(models))
            ),
        )
    )

    assert result.session == (
        "research-session",
        {"resources": []},
        extension_runtime,
        None,
        None,
        "base prompt",
        None,
    )
    assert result.configuration.cwd_bound_services_audit == "audit"
    assert actions[0][0] == "diagnostics"
    assert actions[1][0] == "agent"
    assert actions[1][1]["initial_state"]["system_prompt"] == "assembled prompt"
    assert actions[1][1]["initial_state"]["model"] == "resolved-model"
    assert actions[2][0] == "scoped-models"
    assert disposed == []


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
