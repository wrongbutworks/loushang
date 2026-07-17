from __future__ import annotations

import asyncio
from types import SimpleNamespace

from loushang.ai.model import Auth, Endpoint, Model, Provider
from loushang.ai.model.registry import ModelRegistry as AiModelRegistry
from loushang.coding.control import AuthManager
from loushang.coding.diagnostics import DiagnosticsService
from loushang.coding.session.auth_bridge_controller import AuthBridgeController
from loushang.coding.store import SessionManager


def _registry_with_auth_model() -> tuple[AiModelRegistry, Model]:
    model = Model(id="alpha", provider="proxy", endpoint="default")
    registry = AiModelRegistry(
        {
            "proxy": Provider(
                id="proxy",
                endpoints={
                    "default": Endpoint(
                        id="default",
                        provider="proxy",
                        api="proxy-api",
                        auth=Auth(api_key_env="PROXY_API_KEY"),
                        models={"alpha": model},
                    )
                },
            )
        }
    )
    return registry, registry.get_model("proxy", "default", "alpha")


def test_auth_bridge_controller_wires_agent_api_key_resolver_for_active_model_provider(
    tmp_path,
) -> None:
    registry, model = _registry_with_auth_model()
    agent = SimpleNamespace(model=model, get_api_key=None)
    diagnostics_service = DiagnosticsService()
    controller = AuthBridgeController(
        agent=agent,
        auth_manager=AuthManager(ai_registry=registry, env={"PROXY_API_KEY": "secret"}),
        diagnostics_service=diagnostics_service,
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
    )

    controller.configure_auth_bridge()

    assert agent.get_api_key("proxy") == "secret"
    assert agent.get_api_key("other") is None
    assert diagnostics_service.get_diagnostics() == []


def test_auth_bridge_controller_records_unresolved_model_auth(tmp_path) -> None:
    registry, model = _registry_with_auth_model()
    agent = SimpleNamespace(model=model, get_api_key=None)
    diagnostics_service = DiagnosticsService()
    controller = AuthBridgeController(
        agent=agent,
        auth_manager=AuthManager(ai_registry=registry, env={}),
        diagnostics_service=diagnostics_service,
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
    )

    controller.configure_auth_bridge()

    records = diagnostics_service.get_diagnostics(code="model_auth_unresolved")
    assert len(records) == 1
    assert records[0].type == "warning"
    assert records[0].details == {
        "provider": "proxy",
        "model_id": "alpha",
        "endpoint_id": "default",
        "api_key_env": "PROXY_API_KEY",
        "auth_source": "none",
    }


def test_auth_bridge_controller_records_auth_resolution_failures(tmp_path) -> None:
    registry, model = _registry_with_auth_model()
    agent = SimpleNamespace(model=model, get_api_key=None)
    diagnostics_service = DiagnosticsService()

    class FailingAuthManager:
        def get_api_key_for_model(self, model: Model) -> str | None:
            del model
            return None

        def resolve_for_model(self, model: Model):
            del model
            raise RuntimeError("auth boom")

    controller = AuthBridgeController(
        agent=agent,
        auth_manager=FailingAuthManager(),
        diagnostics_service=diagnostics_service,
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
    )

    controller.record_model_auth_resolution(model)

    records = diagnostics_service.get_diagnostics(code="model_auth_resolution_failed")
    assert len(records) == 1
    assert records[0].type == "error"
    assert records[0].details == {
        "provider": "proxy",
        "model_id": "alpha",
        "endpoint_id": "default",
    }
