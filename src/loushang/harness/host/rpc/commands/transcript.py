"""Transcript query and export commands for the shared RPC host."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from loushang.harness.host.rpc.arguments import optional_string
from loushang.harness.host.rpc.output import RpcOutput
from loushang.harness.host.rpc.routing import LegacyRpcHandler
from loushang.harness.host.rpc.wire import camelize, project_json_value
from loushang.harness.transcript import create_agent_transcript_message_codec

_MESSAGE_CODEC = create_agent_transcript_message_codec()


class RpcTranscriptCommands:
    """Project transcript reads without owning Session or wire lifecycle."""

    def __init__(
        self,
        *,
        get_session: Callable[[], Any],
        get_messages: Callable[[object], object],
        output: RpcOutput,
    ) -> None:
        self._get_session = get_session
        self._get_messages = get_messages
        self._output = output

    def bindings(self) -> tuple[tuple[str, LegacyRpcHandler], ...]:
        return (
            ("get_messages", self.get_messages),
            ("get_last_assistant_text", self.get_last_assistant_text),
            ("get_fork_messages", self.get_fork_messages),
            ("export_html", self.export_html),
        )

    def get_messages(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        messages = self._get_messages(self._get_session())
        if not isinstance(messages, list):
            self._error(
                command_id,
                "get_messages",
                "Message log returned an invalid response.",
            )
            return
        serialized_messages: list[dict[str, Any]] = []
        for message in messages:
            try:
                serialized_messages.append(_MESSAGE_CODEC.serialize(message))
            except Exception:
                continue
        self._output.success(
            request_id=command_id,
            command="get_messages",
            data={"messages": serialized_messages},
        )

    def get_last_assistant_text(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        getter = getattr(self._get_session(), "get_last_assistant_text", None)
        try:
            text = getter() if callable(getter) else None
        except Exception as error:
            self._error(
                command_id,
                "get_last_assistant_text",
                f"Failed to read last assistant text: {error}",
            )
            return
        self._output.success(
            request_id=command_id,
            command="get_last_assistant_text",
            data={"text": text},
        )

    def get_fork_messages(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        del payload
        getter = getattr(self._get_session(), "get_user_messages_for_forking", None)
        if not callable(getter):
            self._error(
                command_id,
                "get_fork_messages",
                "Fork messages are not available.",
            )
            return
        try:
            raw_messages = getter()
        except Exception as error:
            self._error(
                command_id,
                "get_fork_messages",
                f"Failed to query fork messages: {error}",
            )
            return
        if not isinstance(raw_messages, list):
            self._error(
                command_id,
                "get_fork_messages",
                "Fork messages returned an invalid response.",
            )
            return
        self._output.success(
            request_id=command_id,
            command="get_fork_messages",
            data={"messages": camelize(project_json_value(raw_messages))},
        )

    def export_html(
        self, command_id: str | None, payload: dict[str, Any]
    ) -> None:
        output_path = optional_string(payload, "outputPath", "output_path")
        try:
            path = self._get_session().export_to_html(output_path)
        except Exception as error:
            self._error(
                command_id,
                "export_html",
                f"Failed to export HTML: {error}",
            )
            return
        if not isinstance(path, str):
            if isinstance(path, Path):
                path = str(path)
            else:
                self._error(
                    command_id,
                    "export_html",
                    "Export returned an invalid response.",
                )
                return
        self._output.success(
            request_id=command_id,
            command="export_html",
            data={"path": path},
        )

    def _error(self, command_id: str | None, command: str, error: str) -> None:
        self._output.error(
            request_id=command_id,
            command=command,
            error=error,
        )


__all__ = ["RpcTranscriptCommands"]
