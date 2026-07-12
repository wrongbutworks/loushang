from __future__ import annotations

from dataclasses import dataclass

from loushang.ai.model import Model
from loushang.coding.store import SessionManager
from loushang.harness.diagnostics.service import DiagnosticsService


@dataclass
class AuthBridgeController:
    agent: object
    auth_manager: object | None
    diagnostics_service: DiagnosticsService | None
    session_manager: SessionManager

    def configure_auth_bridge(self) -> None:
        if self.auth_manager is None:
            return
        setattr(self.agent, "get_api_key", self.get_runtime_api_key)
        self.record_model_auth_resolution(getattr(self.agent, "model"))

    def get_runtime_api_key(self, provider: str) -> str | None:
        if self.auth_manager is None:
            return None
        model = getattr(self.agent, "model")
        if getattr(model, "provider_id", None) != provider:
            return None
        return self.auth_manager.get_api_key_for_model(model)

    def record_model_auth_resolution(self, model: Model) -> None:
        if self.auth_manager is None:
            return
        try:
            resolution = self.auth_manager.resolve_for_model(model)
        except Exception as exc:
            self.record_model_auth_resolution_failure(model, exc)
            return
        if not resolution.auth_required or resolution.satisfied or self.diagnostics_service is None:
            return
        self.diagnostics_service.capture_failure(
            code="model_auth_unresolved",
            error=resolution.message or f"Missing auth for model '{resolution.provider}:{resolution.model_id}'.",
            phase="runtime",
            source="model",
            level="warning",
            session_id=self.session_manager.get_header().id,
            entry_id=self.session_manager.get_leaf_id(),
            details={
                "provider": resolution.provider,
                "model_id": resolution.model_id,
                "endpoint_id": resolution.endpoint_id,
                "api_key_env": resolution.api_key_env,
                "auth_source": resolution.source,
            },
        )

    def record_model_auth_resolution_failure(self, model: Model, exc: Exception) -> None:
        if self.diagnostics_service is None:
            return
        self.diagnostics_service.capture_failure(
            code="model_auth_resolution_failed",
            error=exc,
            phase="runtime",
            source="model",
            level="error",
            session_id=self.session_manager.get_header().id,
            entry_id=self.session_manager.get_leaf_id(),
            details={
                "provider": model.provider_id,
                "model_id": model.id,
                "endpoint_id": model.endpoint_id,
            },
        )
