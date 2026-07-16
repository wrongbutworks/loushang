from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from loushang.agent.types import AgentToolResult
from loushang.ai.types import AssistantMessage
from loushang.coding.store import SessionManager
from loushang.harness.diagnostics.service import DiagnosticsService
from loushang.harness.diagnostics.types import (
    DiagnosticLevel,
    DiagnosticPhase,
    DiagnosticRecord,
    DiagnosticsQuery,
    DiagnosticSummary,
    ErrorReport,
)
from loushang.harness.resources.diagnostics import ResourceDiagnostic
from loushang.protocol import require_json_value

_EXTENSION_ERROR_DIAGNOSTIC_CODES: frozenset[str] = frozenset(
    {
        "extension_runtime_bind_failed",
        "extension_resource_refresh_failed",
        "extension_session_start_failed",
        "extension_session_refresh_failed",
        "extension_resources_discover_failed",
    }
)


@dataclass
class SessionDiagnosticsBridge:
    diagnostics_service: DiagnosticsService | None
    session_manager: SessionManager
    get_extension_runner: Callable[[], object | None]
    recorded_extension_diagnostics: int = 0

    def get_last_diagnostics(self, limit: int = 50) -> list[DiagnosticRecord]:
        if self.diagnostics_service is None:
            return []
        return self.diagnostics_service.get_last_diagnostics(limit=limit)

    def get_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        if self.diagnostics_service is None:
            return []
        return self.diagnostics_service.get_diagnostics(query=query)

    def get_session_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        if self.diagnostics_service is None:
            return []
        return self.diagnostics_service.get_diagnostics(
            query=_diagnostics_query_for_session(
                query, self.session_manager.get_header().conversation_id
            )
        )

    def get_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        service = self.diagnostics_service or DiagnosticsService()
        return service.get_diagnostics_summary(query=query)

    def get_session_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        service = self.diagnostics_service or DiagnosticsService()
        return service.get_diagnostics_summary(
            query=_diagnostics_query_for_session(
                query, self.session_manager.get_header().conversation_id
            )
        )

    def get_last_error_report(self) -> ErrorReport | None:
        if self.diagnostics_service is None:
            return None
        return self.diagnostics_service.get_last_error_report()

    def record_runtime_exception(self, *, code: str, exc: Exception | str) -> None:
        if self.diagnostics_service is None:
            return
        self.diagnostics_service.capture_failure(
            code=code,
            error=exc,
            phase="runtime",
            source="session",
            session_id=self.session_manager.get_header().conversation_id,
            entry_id=self.session_manager.get_leaf_id(),
        )

    def record_extension_runtime_diagnostic(
        self, diagnostic: ResourceDiagnostic
    ) -> None:
        if self.diagnostics_service is None:
            return
        self.diagnostics_service.record(
            self.diagnostics_service.normalize_resource_diagnostic(
                diagnostic,
                phase="runtime",
                source="extensions",
                session_id=self.session_manager.get_header().conversation_id,
                entry_id=self.session_manager.get_leaf_id(),
                level=_extension_diagnostic_level(diagnostic.code),
            )
        )

    def sync_extension_diagnostics(self, *, phase: DiagnosticPhase) -> None:
        if self.diagnostics_service is None:
            return
        extension_runner = self.get_extension_runner()
        if extension_runner is None:
            return
        get_diagnostics = getattr(extension_runner, "get_diagnostics", None)
        if not callable(get_diagnostics):
            return
        diagnostics = get_diagnostics()
        if self.recorded_extension_diagnostics >= len(diagnostics):
            return
        new_diagnostics = diagnostics[self.recorded_extension_diagnostics :]
        self.diagnostics_service.record_many(
            self.diagnostics_service.normalize_resource_diagnostic(
                diagnostic,
                phase=phase,
                source="extensions",
                session_id=self.session_manager.get_header().conversation_id,
                entry_id=self.session_manager.get_leaf_id(),
                level=_extension_diagnostic_level(diagnostic.code),
            )
            for diagnostic in new_diagnostics
        )
        self.recorded_extension_diagnostics = len(diagnostics)

    def record_assistant_response_error(
        self, assistant_message: AssistantMessage
    ) -> None:
        if self.diagnostics_service is None:
            return
        if (
            assistant_message.stop_reason != "error"
            or not assistant_message.error_message
        ):
            return
        self.diagnostics_service.capture_failure(
            code="assistant_response_error",
            error=assistant_message.error_message,
            phase="runtime",
            source="provider",
            session_id=self.session_manager.get_header().conversation_id,
            entry_id=self.session_manager.get_leaf_id(),
            details={
                "provider": assistant_message.provider,
                "model_id": assistant_message.model,
                "api": assistant_message.api,
                "response_id": assistant_message.response_id,
                "stop_reason": assistant_message.stop_reason,
            },
        )

    def record_tool_execution_error(self, event: Mapping[str, object]) -> None:
        if self.diagnostics_service is None:
            return
        tool_call_id = event.get("tool_call_id")
        tool_name = event.get("tool_name")
        if not isinstance(tool_call_id, str) or not isinstance(tool_name, str):
            return
        result = event.get("result")
        message = _tool_result_error_message(result)
        result_details = _tool_result_details(result)
        self.diagnostics_service.capture_failure(
            code="tool_execution_failed",
            error=message,
            phase="runtime",
            source="tool",
            session_id=self.session_manager.get_header().conversation_id,
            entry_id=self.session_manager.get_leaf_id(),
            details={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "is_error": True,
                "result_details": result_details,
            },
        )
        if _is_policy_result_details(result_details):
            self.diagnostics_service.capture_failure(
                code=_policy_result_code(result_details),
                error=message,
                phase="runtime",
                source="policy",
                level="warning",
                session_id=self.session_manager.get_header().conversation_id,
                entry_id=self.session_manager.get_leaf_id(),
                details=_policy_diagnostic_details(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    result_details=result_details,
                ),
            )


def _extension_diagnostic_level(code: str) -> DiagnosticLevel:
    if code in _EXTENSION_ERROR_DIAGNOSTIC_CODES:
        return "error"
    return "warning"


def _diagnostics_query_for_session(
    query: DiagnosticsQuery | None, session_id: str
) -> DiagnosticsQuery:
    if query is None:
        return DiagnosticsQuery(session_id=session_id)
    return replace(query, session_id=session_id)


def _tool_result_error_message(result: object) -> str:
    content = getattr(result, "content", None)
    if isinstance(content, list):
        texts = [
            part.text
            for part in content
            if getattr(part, "type", None) == "text"
            and isinstance(getattr(part, "text", None), str)
        ]
        if texts:
            return "\n".join(texts)
    return "Tool execution failed."


def _tool_result_details(result: object) -> Mapping[str, object]:
    if isinstance(result, AgentToolResult):
        try:
            details = result.event_details()
        except Exception:
            return {}
    else:
        try:
            details = require_json_value(
                getattr(result, "details", None),
                name="tool_diagnostic.details",
            )
        except TypeError:
            return {}
    return details if isinstance(details, Mapping) else {}


def _is_policy_result_details(details: object) -> bool:
    return isinstance(details, Mapping) and isinstance(
        details.get("policy_disposition"), str
    )


def _policy_result_code(details: Mapping[str, object]) -> str:
    code = details.get("policy_code")
    return code if isinstance(code, str) and code else "tool_policy_denied"


def _policy_diagnostic_details(
    *,
    tool_call_id: str,
    tool_name: str,
    result_details: Mapping[str, object],
) -> dict[str, object]:
    details = {
        key: value
        for key, value in result_details.items()
        if isinstance(value, str | bool | int | float | list | tuple | dict)
        or value is None
    }
    details["tool_call_id"] = tool_call_id
    details["tool_name"] = tool_name
    return details
