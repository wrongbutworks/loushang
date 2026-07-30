"""Diagnostics commands for the shared RPC host."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loushang.harness.diagnostics.types import DiagnosticsQuery
from loushang.harness.host.rpc.arguments import optional_string
from loushang.harness.host.rpc.output import RpcOutput
from loushang.harness.host.rpc.projections import RpcDiagnosticsProjection
from loushang.harness.host.rpc.routing import LegacyRpcHandler


class RpcDiagnosticsCommands:
    """Project runtime/session diagnostics through the existing RPC wire."""

    def __init__(
        self,
        *,
        runtime: object,
        get_session: Callable[[], object],
        output: RpcOutput,
        projection: RpcDiagnosticsProjection,
    ) -> None:
        self._runtime = runtime
        self._get_session = get_session
        self._output = output
        self._projection = projection

    def bindings(self) -> tuple[tuple[str, LegacyRpcHandler], ...]:
        return (
            ("get_diagnostics", self.get_diagnostics),
            ("get_session_diagnostics", self.get_session_diagnostics),
            ("get_diagnostics_summary", self.get_diagnostics_summary),
            (
                "get_session_diagnostics_summary",
                self.get_session_diagnostics_summary,
            ),
            ("get_last_error_report", self.get_last_error_report),
        )

    def get_diagnostics(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._query_records(
            command_id=command_id,
            payload=payload,
            command="get_diagnostics",
            runtime_method="get_diagnostics",
            session_method="get_diagnostics",
            fallback_to_last=True,
        )

    def get_session_diagnostics(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._query_records(
            command_id=command_id,
            payload=payload,
            command="get_session_diagnostics",
            runtime_method="get_session_diagnostics",
            session_method="get_session_diagnostics",
            fallback_to_last=False,
        )

    def get_diagnostics_summary(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._query_summary(
            command_id=command_id,
            payload=payload,
            command="get_diagnostics_summary",
            runtime_method="get_diagnostics_summary",
            session_method="get_diagnostics_summary",
        )

    def get_session_diagnostics_summary(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        self._query_summary(
            command_id=command_id,
            payload=payload,
            command="get_session_diagnostics_summary",
            runtime_method="get_session_diagnostics_summary",
            session_method="get_session_diagnostics_summary",
        )

    def get_last_error_report(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        getter = getattr(self._get_session(), "get_last_error_report", None)
        if not callable(getter):
            self._output.error(
                request_id=command_id,
                command="get_last_error_report",
                error="Diagnostics are not available.",
            )
            return
        try:
            report = self._projection.serialize_error_report(getter())
        except Exception as error:
            self._output.error(
                request_id=command_id,
                command="get_last_error_report",
                error=f"Failed to query last error report: {error}",
            )
            return
        self._output.success(
            request_id=command_id,
            command="get_last_error_report",
            data={"report": report},
        )

    def _query_records(
        self,
        *,
        command_id: str | None,
        payload: dict[str, Any],
        command: str,
        runtime_method: str,
        session_method: str,
        fallback_to_last: bool,
    ) -> None:
        raw_limit = payload.get("limit", 50)
        if not isinstance(raw_limit, int) or raw_limit <= 0:
            self._output.error(
                request_id=command_id,
                command=command,
                error="Diagnostic limit must be a positive integer.",
            )
            return

        query = _query_from_payload(payload, default_limit=raw_limit)
        getter = getattr(self._runtime, runtime_method, None)
        if callable(getter):

            def query_records():
                return getter(query=query)

        else:
            session = self._get_session()
            getter = getattr(session, session_method, None)
            if callable(getter):

                def query_records():
                    return getter(query=query)

            else:
                getter = (
                    getattr(session, "get_last_diagnostics", None)
                    if fallback_to_last
                    else None
                )
                if callable(getter):

                    def query_records():
                        return getter(limit=raw_limit)

        if not callable(getter):
            self._output.error(
                request_id=command_id,
                command=command,
                error="Diagnostics are not available.",
            )
            return
        try:
            raw_diagnostics = query_records()
        except Exception as error:
            self._output.error(
                request_id=command_id,
                command=command,
                error=f"Failed to query diagnostics: {error}",
            )
            return
        if not isinstance(raw_diagnostics, list):
            self._output.error(
                request_id=command_id,
                command=command,
                error="Diagnostics returned an invalid response.",
            )
            return

        diagnostics = []
        for record in raw_diagnostics:
            try:
                diagnostics.append(self._projection.serialize_diagnostic(record))
            except Exception:
                continue
        self._output.success(
            request_id=command_id,
            command=command,
            data={"diagnostics": diagnostics},
        )

    def _query_summary(
        self,
        *,
        command_id: str | None,
        payload: dict[str, Any],
        command: str,
        runtime_method: str,
        session_method: str,
    ) -> None:
        try:
            query = _query_from_payload(payload, default_limit=None)
        except ValueError as error:
            self._output.error(
                request_id=command_id, command=command, error=str(error)
            )
            return
        getter = getattr(self._runtime, runtime_method, None)
        if callable(getter):

            def get_summary():
                return getter(query=query)

        else:
            getter = getattr(self._get_session(), session_method, None)
            if callable(getter):

                def get_summary():
                    return getter(query=query)

        if not callable(getter):
            self._output.error(
                request_id=command_id,
                command=command,
                error="Diagnostics are not available.",
            )
            return
        try:
            summary = self._projection.serialize_diagnostic_summary(get_summary())
        except Exception as error:
            self._output.error(
                request_id=command_id,
                command=command,
                error=f"Failed to query diagnostics: {error}",
            )
            return
        self._output.success(
            request_id=command_id,
            command=command,
            data={"summary": summary},
        )


def _query_from_payload(
    payload: dict[str, Any], *, default_limit: int | None
) -> DiagnosticsQuery:
    raw_limit = payload.get("limit", default_limit)
    if raw_limit is not None and (not isinstance(raw_limit, int) or raw_limit <= 0):
        raise ValueError("Diagnostic limit must be a positive integer.")
    return DiagnosticsQuery(
        phase=optional_string(payload, "phase"),  # type: ignore[arg-type]
        source=optional_string(payload, "source"),  # type: ignore[arg-type]
        level=optional_string(
            payload, "level", "diagnosticType", "diagnostic_type"
        ),  # type: ignore[arg-type]
        session_id=optional_string(payload, "sessionId", "session_id"),
        entry_id=optional_string(payload, "entryId", "entry_id"),
        tool_call_id=optional_string(payload, "toolCallId", "tool_call_id"),
        code=optional_string(payload, "code"),
        limit=raw_limit,
    )


__all__ = ["RpcDiagnosticsCommands"]
