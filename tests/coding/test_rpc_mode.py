from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from loushang.ai.model import ModelSelection
from loushang.ai.model.domain import (
    Capabilities,
    Endpoint,
    Model,
    OpenAICompletionsConfig,
    Pricing,
)
from loushang.ai.types import AssistantMessage, TextPart, Usage, UserMessage
from loushang.harness.commands import CommandSourceInfo, SessionCommandDescriptor
from loushang.harness.conversation import ConversationRecord
from loushang.harness.diagnostics import (
    DiagnosticRecord,
    DiagnosticsQuery,
    DiagnosticSummary,
    ErrorReport,
)
from loushang.harness.events import RuntimeEvent
from loushang.harness.resources.types import (
    PromptFragmentDescriptor,
    ResourceBundle,
    SkillDescriptor,
)
from loushang.harness.runtime import SessionOperationResult
from loushang.harness.runtime.types import RunState
from loushang.harness.session.inspection import AgentSessionState
from loushang.harness.transcript import (
    AGENT_MESSAGE_KIND,
    CompactionResult,
    SessionQuery,
)


def _assistant_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        role="assistant",
        content=[TextPart(type="text", text=text)],
        api="anthropic-messages",
        provider="faux",
        model="faux-model",
        response_id=None,
        usage=Usage(
            input=0, output=0, cache_read=0, cache_write=0, total_tokens=0, cost={}
        ),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


def _user_message(text: str) -> UserMessage:
    return UserMessage(
        role="user",
        content=[TextPart(type="text", text=text)],
        timestamp=0.0,
    )


def _message_record(record_id: str, message: UserMessage) -> ConversationRecord[object]:
    return ConversationRecord(
        record_id=record_id,
        parent_id=None,
        kind=AGENT_MESSAGE_KIND,
        payload_version=1,
        created_at="2026-05-21T00:00:00Z",
        payload=message,
    )


def _parse_jsonl(stream: StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def _command_descriptor(item: dict[str, object]) -> SessionCommandDescriptor:
    source_info = item.get("source_info")
    path = (
        source_info.get("path", "")
        if isinstance(source_info, dict)
        else item.get("path", "")
    )
    path_text = str(path)
    return SessionCommandDescriptor(
        name=item.get("name") if isinstance(item.get("name"), str) else "",
        description=item.get("description")
        if isinstance(item.get("description"), str)
        else None,
        source=item.get("source") if isinstance(item.get("source"), str) else "",
        source_info=CommandSourceInfo(
            path=path_text, base_dir=str(Path(path_text).parent) if path_text else None
        ),
    )


class FakeSessionManager:
    def __init__(self, cwd: str, owner: "FakeSession") -> None:
        self._cwd = cwd
        self._owner = owner
        self.session_info_calls: list[str | None] = []
        self._leaf_id: str | None = "leaf-1"
        self._entries_by_id: dict[str, object] = {}

    def get_cwd(self) -> str:
        return self._cwd

    def get_leaf_id(self) -> str | None:
        return self._leaf_id

    def set_leaf_id(self, leaf_id: str | None) -> None:
        self._leaf_id = leaf_id

    def get_entry(self, entry_id: str):
        return self._entries_by_id.get(entry_id)

    def set_entry(self, entry_id: str, entry: object) -> None:
        self._entries_by_id[entry_id] = entry

    async def append_session_info(self, name: str | None) -> str:
        self.session_info_calls.append(name)
        self._owner.session_name = name
        return "session-info-1"


class FakeAgent:
    def __init__(self) -> None:
        self.steering_mode = "one-at-a-time"
        self.follow_up_mode = "one-at-a-time"


class FakeModelRegistry:
    def __init__(
        self,
        models: list[ModelSelection] | None = None,
        resolved_models: dict[tuple[str, str], Model] | None = None,
        endpoints: dict[tuple[str, str], Endpoint] | None = None,
    ) -> None:
        self._models = list(models or [])
        self._resolved_models = dict(resolved_models or {})
        self._endpoints = dict(endpoints or {})

    def list_models(self) -> list[ModelSelection]:
        return list(self._models)

    def build_model(self, selection: ModelSelection) -> Model:
        key = (selection.provider, selection.model_id)
        try:
            return self._resolved_models[key]
        except KeyError as error:
            raise KeyError(key) from error

    def get_endpoint(self, provider: str, endpoint: str) -> Endpoint | None:
        return self._endpoints.get((provider, endpoint))


class FakeSession:
    def __init__(
        self,
        *,
        session_id: str,
        cwd: str,
        session_name: str | None = None,
        event_message: AssistantMessage | None = None,
        messages: list[object] | None = None,
    ) -> None:
        self.session_id = session_id
        self.session_name = session_name
        self.session_file = Path(cwd) / f"{session_id}.jsonl"
        self.agent = FakeAgent()
        self.session_manager = FakeSessionManager(cwd, self)
        self.model_registry = FakeModelRegistry()
        self.resource_bundle = ResourceBundle(cwd=Path(cwd))
        self.listeners = []
        self.prompt_calls: list[tuple[str, object]] = []
        self.prompt_kwargs: list[dict[str, object]] = []
        self.wait_calls = 0
        self.steer_calls: list[tuple[str, object]] = []
        self.follow_up_calls: list[tuple[str, object]] = []
        self.abort_calls = 0
        self.set_model_calls: list[ModelSelection] = []
        self.set_active_tools_calls: list[list[str]] = []
        self.set_thinking_level_calls: list[str] = []
        self.set_steering_mode_calls: list[str] = []
        self.set_follow_up_mode_calls: list[str] = []
        self.set_session_name_calls: list[str | None] = []
        self.set_auto_retry_calls: list[bool] = []
        self.set_auto_compaction_calls: list[bool] = []
        self.command_entries: list[dict[str, object]] = []
        self.diagnostics: list[DiagnosticRecord] = []
        self.packages: list[dict[str, object]] = []
        self.error_report: ErrorReport | None = None
        self.abort_retry_calls = 0
        self.compact_calls: list[str | None] = []
        self.bash_calls: list[dict[str, object]] = []
        self.abort_bash_calls = 0
        self.export_to_html_calls: list[str | None] = []
        self.user_messages_for_forking: list[dict[str, str]] = []
        self._bash_started: asyncio.Event | None = None
        self._bash_release: asyncio.Event | None = None
        self._bash_result: dict[str, object] = {
            "output": "ok\n",
            "exit_code": 0,
            "cancelled": False,
            "truncated": False,
            "full_output_path": None,
        }
        self._event_message = event_message
        self._messages = list(messages or [])
        self._prompt_started: asyncio.Event | None = None
        self._prompt_release: asyncio.Event | None = None
        self._state = AgentSessionState(
            run=RunState(status="idle"),
            steering=[],
            follow_up=[],
            active_tool_names=[],
            is_compacting=False,
            is_retrying=False,
            thinking_level="off",
            model_selection=None,
        )

    @property
    def session_control(self) -> "FakeSession":
        return self

    def subscribe(self, listener):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    def get_state(self) -> AgentSessionState:
        return self._state

    def get_model_selection(self) -> ModelSelection | None:
        return self._state.model_selection

    def get_session_context(self):
        return SimpleNamespace(messages=tuple(self._messages))

    async def prompt(self, user_input: str, images=None, **kwargs) -> None:
        self.prompt_calls.append((user_input, images))
        self.prompt_kwargs.append(dict(kwargs))
        preflight_result = kwargs.get("preflight_result")
        if callable(preflight_result):
            preflight_result(True)
        streaming_behavior = kwargs.get("streaming_behavior")
        if self._state.run.status == "running" and streaming_behavior in {
            "steer",
            "followUp",
            "follow_up",
        }:
            if streaming_behavior == "steer":
                self.steer(user_input, images=images)
            else:
                self.follow_up(user_input, images=images)
            return
        self._state = replace(self._state, run=RunState(status="running"))
        if self._prompt_started is not None:
            self._prompt_started.set()
        if self._prompt_release is not None:
            await self._prompt_release.wait()
        if self._event_message is not None:
            self._messages.append(self._event_message)
            for listener in list(self.listeners):
                listener({"type": "message_end", "message": self._event_message})
        self._state = replace(self._state, run=RunState(status="idle"))

    async def wait_for_idle(self) -> None:
        self.wait_calls += 1

    def steer(self, user_input: str, images=None) -> None:
        self.steer_calls.append((user_input, images))
        self._state = replace(self._state, steering=[*self._state.steering, user_input])

    def follow_up(self, user_input: str, images=None) -> None:
        self.follow_up_calls.append((user_input, images))
        self._state = replace(
            self._state, follow_up=[*self._state.follow_up, user_input]
        )

    def abort(self) -> None:
        self.abort_calls += 1

    async def set_model(self, selection: ModelSelection) -> None:
        self.set_model_calls.append(selection)
        self._state = replace(self._state, model_selection=selection)

    async def cycle_model(self) -> ModelSelection | None:
        models = self.get_available_models()
        if not isinstance(models, list):
            raise TypeError("Model registry returned an invalid response.")
        if not models:
            return None
        current = self.get_model_selection()
        try:
            index = models.index(current) if current is not None else -1
        except ValueError:
            index = -1
        selection = models[(index + 1) % len(models)]
        await self.set_model(selection)
        return selection

    async def set_active_tools(self, tool_names: list[str]) -> None:
        self.set_active_tools_calls.append(list(tool_names))
        self._state = replace(self._state, active_tool_names=list(tool_names))

    def set_thinking_level(self, level: str) -> None:
        self.set_thinking_level_calls.append(level)
        self._state = replace(self._state, thinking_level=level)

    def cycle_thinking_level(self) -> str:
        order = ("off", "minimal", "low", "medium", "high", "xhigh")
        try:
            index = order.index(self._state.thinking_level)
        except ValueError:
            index = 0
        next_level = order[(index + 1) % len(order)]
        self.set_thinking_level(next_level)
        return next_level

    def set_steering_mode(self, mode: str) -> None:
        self.set_steering_mode_calls.append(mode)
        self.agent.steering_mode = mode

    def set_follow_up_mode(self, mode: str) -> None:
        self.set_follow_up_mode_calls.append(mode)
        self.agent.follow_up_mode = mode

    async def set_session_name(self, name: str | None) -> None:
        self.set_session_name_calls.append(name)
        await self.session_manager.append_session_info(name)

    def get_available_models(self) -> list[ModelSelection]:
        return self.model_registry.list_models()

    def list_commands(self) -> list[object]:
        if self.command_entries:
            return [
                command
                if isinstance(command, SessionCommandDescriptor)
                else _command_descriptor(command)
                for command in self.command_entries
            ]
        commands: list[SessionCommandDescriptor] = []
        for prompt in self.resource_bundle.prompts:
            commands.append(
                _command_descriptor(
                    {
                        "name": f"/{prompt.name}",
                        "source": "prompt",
                        "path": str(prompt.source_path),
                    }
                )
            )
        for skill in self.resource_bundle.skills:
            commands.append(
                _command_descriptor(
                    {
                        "name": f"/skill:{skill.name}",
                        "source": "skill",
                        "path": str(skill.source_path),
                    }
                )
            )
        return commands

    def get_last_diagnostics(self, limit: int = 50) -> list[DiagnosticRecord]:
        return self.diagnostics[-limit:]

    def get_last_error_report(self) -> ErrorReport | None:
        return self.error_report

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        self.set_auto_retry_calls.append(enabled)

    @property
    def auto_compaction_enabled(self) -> bool:
        return (
            True
            if not self.set_auto_compaction_calls
            else self.set_auto_compaction_calls[-1]
        )

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        self.set_auto_compaction_calls.append(enabled)

    def abort_retry(self) -> None:
        self.abort_retry_calls += 1

    async def execute_bash(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env=None,
        timeout_seconds: float | None = None,
        stdin: str | None = None,
    ) -> dict[str, object]:
        self.bash_calls.append(
            {
                "command": command,
                "cwd": cwd,
                "env": env,
                "timeout_seconds": timeout_seconds,
                "stdin": stdin,
            }
        )
        if self._bash_started is not None:
            self._bash_started.set()
        if self._bash_release is not None:
            await self._bash_release.wait()
        return dict(self._bash_result)

    def abort_bash(self) -> None:
        self.abort_bash_calls += 1
        if self._bash_release is not None:
            self._bash_result = {
                "output": "partial\n",
                "exit_code": None,
                "cancelled": True,
                "truncated": False,
                "full_output_path": None,
            }
            self._bash_release.set()

    async def compact(self, custom_instructions: str | None = None) -> CompactionResult:
        self.compact_calls.append(custom_instructions)
        return CompactionResult(
            summary="compacted",
            first_kept_entry_id="entry-1",
            tokens_before=42,
            details={"preserved": 3},
        )

    def get_session_stats(self):
        model_selection = self._state.model_selection
        return {
            "sessionId": self.session_id,
            "sessionName": self.session_name,
            "entryCount": 7,
            "messageCount": 5,
            "customMessageCount": 1,
            "activeToolCount": len(self._state.active_tool_names),
            "isRetrying": self._state.is_retrying,
            "isCompacting": self._state.is_compacting,
            "hasDiagnostics": False,
            "branchCount": 2,
            "lastModelSelection": (
                None
                if model_selection is None
                else {
                    "provider": model_selection.provider,
                    "modelId": model_selection.model_id,
                }
            ),
            "contextUsage": {
                "messageCount": 5,
                "assistantMessageCount": 2,
                "userMessageCount": 2,
                "toolCallCount": 1,
                "toolResultCount": 1,
                "customMessageCount": 1,
                "estimatedContextTokens": 123,
                "hasCompaction": False,
                "branchDepth": 2,
                "leafEntryId": "leaf-1",
            },
        }

    def export_to_html(self, output_path: str | None = None) -> str:
        self.export_to_html_calls.append(output_path)
        return output_path or f"/tmp/{self.session_id}.html"

    def get_last_assistant_text(self) -> str | None:
        for message in reversed(self._messages):
            if getattr(message, "role", None) != "assistant":
                continue
            return "".join(
                block.text
                for block in message.content
                if getattr(block, "type", None) == "text"
            )
        return None

    def get_user_messages_for_forking(self) -> list[dict[str, str]]:
        return [
            {"entry_id": item["entry_id"], "text": item["text"]}
            for item in self.user_messages_for_forking
        ]

    def get_entry_text(self, entry_id: str) -> str | None:
        entry = self.session_manager.get_entry(entry_id)
        if entry is None:
            return None
        content = getattr(getattr(entry, "payload", None), "content", None)
        if isinstance(content, str):
            return content or None
        if isinstance(content, list):
            text = "".join(
                block.text
                for block in content
                if getattr(block, "type", None) == "text"
            )
            return text or None
        return None

    def get_packages(
        self, *, catalog_path: str | None = None
    ) -> list[dict[str, object]]:
        del catalog_path
        return list(self.packages)


class FakeRuntime:
    def __init__(
        self, session: FakeSession, session_summaries: list[object] | None = None
    ) -> None:
        self._current_session = session
        self.new_session_calls: list[dict[str, object]] = []
        self.switch_session_calls: list[object] = []
        self.fork_session_calls: list[str] = []
        self.fork_session_operation_calls: list[tuple[str | None, str]] = []
        self._next_session: FakeSession | None = None
        self.session_summaries = list(session_summaries or [])
        self.list_session_summaries_calls = 0
        self.find_session_summaries_calls: list[SessionQuery | None] = []
        self.find_all_session_summaries_calls: list[SessionQuery | None] = []
        self.refresh_session_index_calls = 0
        self.refresh_all_session_indexes_calls = 0
        self.list_indexed_session_summaries_calls = 0
        self.list_all_indexed_session_summaries_calls = 0
        self.find_indexed_session_summaries_calls: list[SessionQuery | None] = []
        self.find_all_indexed_session_summaries_calls: list[SessionQuery | None] = []
        self.diagnostics: list[DiagnosticRecord] = []
        self.get_diagnostics_calls: list[DiagnosticsQuery | None] = []
        self.get_session_diagnostics_calls: list[DiagnosticsQuery | None] = []
        self.get_diagnostics_summary_calls: list[DiagnosticsQuery | None] = []
        self.get_session_diagnostics_summary_calls: list[DiagnosticsQuery | None] = []
        self.get_packages_calls: list[str | None] = []
        self.materialize_package_calls: list[str] = []
        self.install_package_calls: list[str] = []
        self.update_package_calls: list[str] = []
        self.update_packages_calls = 0
        self.check_package_updates_calls = 0
        self.remove_package_calls: list[str] = []
        self.uninstall_package_calls: list[str] = []

    def get_current_session(self) -> FakeSession:
        return self._current_session

    def queue_next_session(self, session: FakeSession) -> None:
        self._next_session = session

    async def new_session_operation(self, *, cwd=None, parent_session=None):
        self.new_session_calls.append({"cwd": cwd, "parent_session": parent_session})
        assert self._next_session is not None
        previous = self._current_session
        self._current_session = self._next_session
        self._next_session = None
        return SessionOperationResult(
            previous=previous,
            current=self._current_session,
            payload=None,
            cancelled=False,
        )

    async def restore_session_operation(self, session_id):
        self.switch_session_calls.append(session_id)
        assert self._next_session is not None
        previous = self._current_session
        self._current_session = self._next_session
        self._next_session = None
        return SessionOperationResult(
            previous=previous,
            current=self._current_session,
            payload=None,
            cancelled=False,
        )

    async def fork_session_operation(
        self, entry_id: str | None, *, position: str = "at"
    ):
        self.fork_session_operation_calls.append((entry_id, position))
        assert self._next_session is not None
        resolved_entry_id = entry_id
        if resolved_entry_id is None:
            resolved_entry_id = self._current_session.session_manager.get_leaf_id()
            if not isinstance(resolved_entry_id, str) or not resolved_entry_id:
                raise ValueError("Cannot clone session: no current entry selected")
        self.fork_session_calls.append(resolved_entry_id)
        selected_text = (
            self._current_session.get_entry_text(resolved_entry_id)
            if entry_id is not None and position == "before"
            else None
        )
        previous = self._current_session
        self._current_session = self._next_session
        self._next_session = None
        return SessionOperationResult(
            previous=previous,
            current=self._current_session,
            payload=selected_text,
            cancelled=False,
        )

    def list_session_summaries(self) -> list[object]:
        self.list_session_summaries_calls += 1
        return list(self.session_summaries)

    def find_session_summaries(self, query: SessionQuery | None = None) -> list[object]:
        self.find_session_summaries_calls.append(query)
        return self._find_session_summaries(query)

    def find_all_session_summaries(
        self, query: SessionQuery | None = None
    ) -> list[object]:
        self.find_all_session_summaries_calls.append(query)
        return self._find_session_summaries(query)

    def refresh_session_index(self) -> list[object]:
        self.refresh_session_index_calls += 1
        return list(self.session_summaries)

    def refresh_all_session_indexes(self) -> list[object]:
        self.refresh_all_session_indexes_calls += 1
        return list(self.session_summaries)

    def list_indexed_session_summaries(self) -> list[object]:
        self.list_indexed_session_summaries_calls += 1
        return list(self.session_summaries)

    def list_all_indexed_session_summaries(self) -> list[object]:
        self.list_all_indexed_session_summaries_calls += 1
        return list(self.session_summaries)

    def find_indexed_session_summaries(
        self, query: SessionQuery | None = None
    ) -> list[object]:
        self.find_indexed_session_summaries_calls.append(query)
        return self._find_session_summaries(query)

    def find_all_indexed_session_summaries(
        self, query: SessionQuery | None = None
    ) -> list[object]:
        self.find_all_indexed_session_summaries_calls.append(query)
        return self._find_session_summaries(query)

    def _find_session_summaries(
        self, query: SessionQuery | None = None
    ) -> list[object]:
        if query is None:
            return list(self.session_summaries)

        def matches(summary: object) -> bool:
            if query.cwd is not None and getattr(summary, "cwd", None) != query.cwd:
                return False
            if (
                query.name is not None
                and query.name.lower() not in str(getattr(summary, "name", "")).lower()
            ):
                return False
            if (
                query.parent_session is not None
                and getattr(summary, "parent_session", None) != query.parent_session
            ):
                return False
            if query.text is not None:
                haystack = " ".join(
                    str(value)
                    for value in (
                        getattr(summary, "session_id", ""),
                        getattr(summary, "cwd", ""),
                        getattr(summary, "name", ""),
                        getattr(summary, "last_message_preview", ""),
                    )
                ).lower()
                if query.text.lower() not in haystack:
                    return False
            return True

        filtered = [summary for summary in self.session_summaries if matches(summary)]
        return filtered[: query.limit] if query.limit is not None else filtered

    def get_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        self.get_diagnostics_calls.append(query)
        return self._filter_diagnostics(
            query, records=list(self.diagnostics or self._current_session.diagnostics)
        )

    def get_session_diagnostics(
        self, query: DiagnosticsQuery | None = None
    ) -> list[DiagnosticRecord]:
        self.get_session_diagnostics_calls.append(query)
        records = list(self.diagnostics or self._current_session.diagnostics)
        records = [
            record
            for record in records
            if record.session_id == self._current_session.session_id
        ]
        return self._filter_diagnostics(query, records=records)

    def get_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        self.get_diagnostics_summary_calls.append(query)
        return _diagnostics_summary(
            self._filter_diagnostics(
                query,
                records=list(self.diagnostics or self._current_session.diagnostics),
            )
        )

    def get_session_diagnostics_summary(
        self, query: DiagnosticsQuery | None = None
    ) -> DiagnosticSummary:
        self.get_session_diagnostics_summary_calls.append(query)
        records = list(self.diagnostics or self._current_session.diagnostics)
        records = [
            record
            for record in records
            if record.session_id == self._current_session.session_id
        ]
        return _diagnostics_summary(self._filter_diagnostics(query, records=records))

    def get_packages(
        self, *, catalog_path: str | None = None
    ) -> list[dict[str, object]]:
        self.get_packages_calls.append(catalog_path)
        return self._current_session.get_packages(catalog_path=catalog_path)

    async def materialize_package(self, source: str) -> dict[str, object]:
        self.materialize_package_calls.append(source)
        return {
            "source": source,
            "name": "review-pack",
            "lifecycle": "materialization_pending",
            "targetPath": "/tmp/packages/review-pack",
            "errorMessage": None,
        }

    async def install_package(self, source: str) -> dict[str, object]:
        self.install_package_calls.append(source)
        return {
            "source": source,
            "name": "review-pack",
            "lifecycle": "installed",
            "targetPath": "/tmp/packages/review-pack",
            "errorMessage": None,
        }

    async def update_package(self, source: str) -> dict[str, object]:
        self.update_package_calls.append(source)
        return {
            "source": source,
            "name": "review-pack",
            "lifecycle": "installed",
            "targetPath": "/tmp/packages/review-pack",
            "errorMessage": None,
        }

    async def update_packages(self) -> list[dict[str, object]]:
        self.update_packages_calls += 1
        return [
            {
                "source": "https://packages.example.invalid/review-pack.git",
                "name": "review-pack",
                "lifecycle": "installed",
                "targetPath": "/tmp/packages/review-pack",
                "errorMessage": None,
            }
        ]

    async def check_package_updates(self) -> list[dict[str, object]]:
        self.check_package_updates_calls += 1
        return [
            {
                "source": "https://packages.example.invalid/review-pack.git",
                "name": "review-pack",
                "currentCommit": "a",
                "availableCommit": "b",
                "pinned": False,
            }
        ]

    async def remove_package(self, source: str) -> dict[str, object]:
        self.remove_package_calls.append(source)
        return {
            "source": source,
            "name": "review-pack",
            "lifecycle": "remote_registered",
            "targetPath": "/tmp/packages/review-pack",
            "errorMessage": None,
        }

    async def uninstall_package(self, source: str) -> dict[str, object]:
        self.uninstall_package_calls.append(source)
        return {
            "source": source,
            "name": "review-pack",
            "lifecycle": "remote_registered",
            "targetPath": "/tmp/packages/review-pack",
            "errorMessage": None,
        }

    def _filter_diagnostics(
        self,
        query: DiagnosticsQuery | None,
        *,
        records: list[DiagnosticRecord],
    ) -> list[DiagnosticRecord]:
        if query is None:
            return records
        if query.phase is not None:
            records = [record for record in records if record.phase == query.phase]
        if query.source is not None:
            records = [record for record in records if record.source == query.source]
        if query.level is not None:
            records = [record for record in records if record.type == query.level]
        if query.session_id is not None:
            records = [
                record for record in records if record.session_id == query.session_id
            ]
        if query.entry_id is not None:
            records = [
                record for record in records if record.entry_id == query.entry_id
            ]
        if query.code is not None:
            records = [record for record in records if record.code == query.code]
        return records[-query.limit :] if query.limit is not None else records


def _diagnostics_summary(records: list[DiagnosticRecord]) -> DiagnosticSummary:
    latest_error = next(
        (record for record in reversed(records) if record.type == "error"), None
    )
    by_code: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_phase: dict[str, int] = {}
    for record in records:
        count = max(record.occurrence_count, 1)
        by_code[record.code] = by_code.get(record.code, 0) + count
        by_source[record.source] = by_source.get(record.source, 0) + count
        by_phase[record.phase] = by_phase.get(record.phase, 0) + count
    return DiagnosticSummary(
        total_count=sum(by_code.values()),
        error_count=sum(
            max(record.occurrence_count, 1)
            for record in records
            if record.type == "error"
        ),
        warning_count=sum(
            max(record.occurrence_count, 1)
            for record in records
            if record.type == "warning"
        ),
        info_count=sum(
            max(record.occurrence_count, 1)
            for record in records
            if record.type == "info"
        ),
        by_code=by_code,
        by_source=by_source,
        by_phase=by_phase,
        latest_error=latest_error,
    )


def test_rpc_mode_runs_prompt_command_and_streams_events() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(
        session_id="session-a",
        cwd="/tmp/project",
        event_message=_assistant_message("done"),
    )
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "c1", "type": "prompt", "message": "hello"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()

        assert exit_code == 0
        assert session.prompt_calls == [("hello", None)]
        assert session.wait_calls == 1

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert lines[0] == {
        "id": "c1",
        "type": "response",
        "command": "prompt",
        "success": True,
    }
    assert lines[1]["type"] == "message_end"
    assert lines[1]["message"]["role"] == "assistant"
    assert lines[1]["message"]["content"][0]["text"] == "done"


def test_rpc_mode_projects_stream_event_shape_and_tool_correlation() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.ai.types import TextPart
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(runtime=runtime, stdin=StringIO(), stdout=stdout, event_view="tools")
    for listener in list(session.listeners):
        listener(
            {
                "type": "tool_execution_update",
                "tool_call_id": "tc1",
                "tool_name": "bash",
                "args": {"cmd": "echo hi"},
                "partial_result": AgentToolResult(
                    content=[TextPart(type="text", text="running")],
                    details={"progress": 0.5},
                ),
            }
        )

    event = _parse_jsonl(stdout)[0]
    assert event["type"] == "tool_execution_update"
    assert event["event_type"] == "tool_execution_update"
    assert event["correlation_id"] == "tc1"
    assert event["stream"] == {
        "kind": "session_event",
        "view": "tools",
        "correlation_id": "tc1",
    }
    assert event["tool_call_id"] == "tc1"
    assert event["tool_name"] == "bash"


def test_rpc_mode_prefers_common_runtime_event_stream() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime_listeners = []

    def subscribe_runtime_events(listener):
        runtime_listeners.append(listener)

        def unsubscribe() -> None:
            runtime_listeners.remove(listener)

        return unsubscribe

    session.subscribe_runtime_events = subscribe_runtime_events
    stdout = StringIO()
    RpcMode(runtime=FakeRuntime(session), stdin=StringIO(), stdout=stdout)

    for listener in list(runtime_listeners):
        listener(
            RuntimeEvent(
                event_id="event-1",
                kind="agent.agent_start",
                stream_id="session:session-a",
                sequence=1,
                occurred_at=datetime(2026, 7, 19, tzinfo=UTC),
                payload={"type": "agent_start"},
            )
        )

    assert session.listeners == []
    assert _parse_jsonl(stdout) == [
        {
            "type": "agent_start",
            "event_type": "agent_start",
            "stream": {"kind": "session_event", "view": "full"},
        }
    ]


def test_rpc_mode_can_include_rendered_tool_event_payloads() -> None:
    from loushang.agent.types import AgentToolResult
    from loushang.ai.types import TextPart
    from loushang.harness.host.rpc import RpcHost as RpcMode
    from loushang.harness.tools.workspace import ToolDefinition

    async def execute(tool_call_id, params, signal=None, on_update=None):
        del tool_call_id, params, signal, on_update
        return AgentToolResult(content=[TextPart(type="text", text="ok")], details={})

    def render_call(args, theme, context):
        del theme
        context.state["command"] = args["command"]
        return {"text": f"call {args['command']}"}

    def render_result(result, options, theme, context):
        del theme
        return {
            "text": f"{context.state['command']} {result.content[0].text} partial={options.is_partial}"
        }

    definition = ToolDefinition(
        name="bash",
        label="Bash",
        description="Run commands",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        execute=execute,
        render_call=render_call,
        render_result=render_result,
    )
    session = FakeSession(session_id="session-a", cwd="/tmp/project")

    def get_tool_definition(name):
        return definition if name == "bash" else None

    session.get_tool_definition = get_tool_definition
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(
        runtime=runtime,
        stdin=StringIO(),
        stdout=stdout,
        event_view="tools",
        render_tool_events=True,
    )
    for listener in list(session.listeners):
        listener(
            {
                "type": "tool_execution_start",
                "tool_call_id": "tc1",
                "tool_name": "bash",
                "args": {"command": "echo hi"},
            }
        )
        listener(
            {
                "type": "tool_execution_update",
                "tool_call_id": "tc1",
                "tool_name": "bash",
                "args": {"command": "echo hi"},
                "partial_result": AgentToolResult(
                    content=[TextPart(type="text", text="running")], details={}
                ),
            }
        )

    lines = _parse_jsonl(stdout)
    assert lines[0]["rendered_tool_call"] == {
        "type": "text",
        "text": "call echo hi",
        "plain_text": "call echo hi",
        "contract_version": 1,
        "status": "running",
    }
    assert lines[1]["rendered_tool_result"] == {
        "type": "text",
        "text": "echo hi running partial=True",
        "plain_text": "echo hi running partial=True",
        "is_partial": True,
        "expanded": False,
        "contract_version": 1,
        "status": "partial",
        "collapsed_text": "echo hi running partial=True",
        "artifacts": [],
    }


def test_rpc_mode_get_state_and_messages_serialize_current_session() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    assistant = _assistant_message("ready")
    session = FakeSession(
        session_id="session-a",
        session_name="Alpha",
        cwd="/tmp/project",
        messages=[assistant],
    )
    session.model_registry = FakeModelRegistry(
        resolved_models={
            ("faux", "alpha"): Model(
                id="alpha",
                provider="faux",
                endpoint="coding",
                name="Faux Alpha",
                capabilities=Capabilities(
                    input=("text",),
                    context_window=200_000,
                    max_tokens=8_192,
                    reasoning=True,
                ),
                pricing=Pricing(input=1.5, output=2.5, cache_read=0.1, cache_write=0.2),
                adapter=OpenAICompletionsConfig(reasoning_effort=True),
            )
        },
        endpoints={
            ("faux", "coding"): Endpoint(
                id="coding",
                api="openai-completions",
                provider="faux",
                base_url="https://api.faux.test/v1",
            )
        },
    )
    asyncio.run(session.set_model(ModelSelection(provider="faux", model_id="alpha")))
    asyncio.run(session.set_active_tools(["bash", "read"]))
    session.steer("first steer")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "state", "type": "get_state"}),
                json.dumps({"id": "messages", "type": "get_messages"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    state_response, messages_response = _parse_jsonl(stdout)
    assert state_response["type"] == "response"
    assert state_response["command"] == "get_state"
    assert state_response["data"]["sessionId"] == "session-a"
    assert state_response["data"]["sessionName"] == "Alpha"
    assert state_response["data"]["sessionFile"] == "/tmp/project/session-a.jsonl"
    assert state_response["data"]["isStreaming"] is False
    assert state_response["data"]["model"] == {
        "provider": "faux",
        "id": "alpha",
        "name": "Faux Alpha",
        "api": "openai-completions",
        "baseUrl": "https://api.faux.test/v1",
        "input": ["text"],
        "contextWindow": 200_000,
        "maxTokens": 8_192,
        "reasoning": True,
        "cost": {
            "input": 1.5,
            "output": 2.5,
            "cacheRead": 0.1,
            "cacheWrite": 0.2,
        },
    }
    assert "cwd" not in state_response["data"]
    assert "modelSelection" not in state_response["data"]
    assert "activeToolNames" not in state_response["data"]
    assert "run" not in state_response["data"]
    assert "steering" not in state_response["data"]
    assert "followUp" not in state_response["data"]
    assert "isRetrying" not in state_response["data"]
    assert "autoRetryEnabled" not in state_response["data"]

    assert messages_response["type"] == "response"
    assert messages_response["command"] == "get_messages"
    assert messages_response["data"]["messages"][0]["role"] == "assistant"
    assert messages_response["data"]["messages"][0]["content"][0]["text"] == "ready"


def test_rpc_mode_list_sessions_uses_runtime_summaries() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(
        session,
        session_summaries=[
            SimpleNamespace(
                session_id="session-b",
                cwd="/tmp/project-b",
                session_file=Path("/tmp/session-b.jsonl"),
                parent_session="/tmp/session-a.jsonl",
                leaf_id="leaf-b",
                created_at="2026-05-21T10:00:00Z",
                updated_at="2026-05-22T10:00:00Z",
                name="Beta",
                message_count=4,
                entry_count=6,
                first_message="first beta prompt",
                all_messages_text="first beta prompt latest message",
                last_message_preview="latest message",
                model={"provider": "faux", "model_id": "beta"},
            )
        ],
    )
    stdin = StringIO(json.dumps({"id": "sessions", "type": "list_sessions"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.find_session_summaries_calls == [SessionQuery()]
    assert runtime.list_session_summaries_calls == 0
    assert response["type"] == "response"
    assert response["command"] == "list_sessions"
    assert response["data"]["sessions"] == [
        {
            "sessionId": "session-b",
            "cwd": "/tmp/project-b",
            "sessionFile": "/tmp/session-b.jsonl",
            "parentSession": "/tmp/session-a.jsonl",
            "leafId": "leaf-b",
            "createdAt": "2026-05-21T10:00:00Z",
            "updatedAt": "2026-05-22T10:00:00Z",
            "name": "Beta",
            "messageCount": 4,
            "entryCount": 6,
            "firstMessage": "first beta prompt",
            "allMessagesText": "first beta prompt latest message",
            "lastMessagePreview": "latest message",
            "model": {"provider": "faux", "modelId": "beta"},
        }
    ]


def test_rpc_mode_list_sessions_supports_query_filters() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(
        session,
        session_summaries=[
            SimpleNamespace(
                session_id="session-alpha",
                cwd="/tmp/project-a",
                session_file=Path("/tmp/session-alpha.jsonl"),
                parent_session=None,
                leaf_id="leaf-alpha",
                created_at="2026-05-21T10:00:00Z",
                updated_at="2026-05-22T10:00:00Z",
                name="Alpha",
                message_count=2,
                entry_count=4,
                last_message_preview="alpha repository task",
                model=None,
            ),
            SimpleNamespace(
                session_id="session-beta",
                cwd="/tmp/project-b",
                session_file=Path("/tmp/session-beta.jsonl"),
                parent_session="/tmp/session-alpha.jsonl",
                leaf_id="leaf-beta",
                created_at="2026-05-22T10:00:00Z",
                updated_at="2026-05-23T10:00:00Z",
                name="Beta",
                message_count=3,
                entry_count=5,
                last_message_preview="beta follow up",
                model=None,
            ),
        ],
    )
    stdin = StringIO(
        json.dumps(
            {
                "id": "sessions",
                "type": "list_sessions",
                "name": "bet",
                "parentSession": "/tmp/session-alpha.jsonl",
                "text": "follow",
                "hasDiagnostics": True,
                "limit": 1,
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.find_session_summaries_calls == [
        SessionQuery(
            name="bet",
            parent_session="/tmp/session-alpha.jsonl",
            text="follow",
            has_diagnostics=True,
            limit=1,
        )
    ]
    assert [item["sessionId"] for item in response["data"]["sessions"]] == [
        "session-beta"
    ]


def test_rpc_mode_list_sessions_supports_all_sessions() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(
        session,
        session_summaries=[
            SimpleNamespace(
                session_id="session-global",
                cwd="/tmp/project-global",
                session_file=Path("/tmp/session-global.jsonl"),
                parent_session=None,
                leaf_id="leaf-global",
                created_at="2026-05-22T10:00:00Z",
                updated_at="2026-05-23T10:00:00Z",
                name="Global",
                message_count=3,
                entry_count=5,
                last_message_preview="global lookup",
                model=None,
            )
        ],
    )
    stdin = StringIO(
        json.dumps(
            {
                "id": "sessions",
                "type": "list_sessions",
                "allSessions": True,
                "text": "lookup",
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.find_all_session_summaries_calls == [SessionQuery(text="lookup")]
    assert runtime.find_session_summaries_calls == []
    assert [item["sessionId"] for item in response["data"]["sessions"]] == [
        "session-global"
    ]


def test_rpc_mode_list_sessions_can_use_indexed_summaries() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(
        session,
        session_summaries=[
            SimpleNamespace(
                session_id="session-indexed",
                cwd="/tmp/project-indexed",
                session_file=Path("/tmp/session-indexed.jsonl"),
                parent_session=None,
                leaf_id=None,
                created_at="2026-05-22T10:00:00Z",
                updated_at="2026-05-23T10:00:00Z",
                name="Indexed",
                message_count=3,
                entry_count=5,
                last_message_preview="indexed lookup",
                model=None,
            )
        ],
    )
    stdin = StringIO(
        json.dumps(
            {
                "id": "sessions",
                "type": "list_sessions",
                "useIndex": True,
                "text": "lookup",
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.find_indexed_session_summaries_calls == [SessionQuery(text="lookup")]
    assert runtime.find_session_summaries_calls == []
    assert [item["sessionId"] for item in response["data"]["sessions"]] == [
        "session-indexed"
    ]


def test_rpc_mode_list_sessions_refresh_index_uses_indexed_all_session_query() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps(
            {
                "id": "sessions",
                "type": "list_sessions",
                "allSessions": True,
                "refreshIndex": True,
                "text": "global",
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert runtime.refresh_all_session_indexes_calls == 1
    assert runtime.find_all_indexed_session_summaries_calls == [
        SessionQuery(text="global")
    ]
    assert runtime.find_all_session_summaries_calls == []


def test_rpc_mode_list_sessions_rejects_invalid_limit() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "sessions", "type": "list_sessions", "limit": -1}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert response == {
        "id": "sessions",
        "type": "response",
        "command": "list_sessions",
        "success": False,
        "error": "Session limit must be non-negative.",
    }


def test_rpc_mode_get_state_omits_optional_fields_when_unset() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.session_file = None
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    state_response = _parse_jsonl(stdout)[0]
    assert state_response["command"] == "get_state"
    assert "sessionName" not in state_response["data"]
    assert "sessionFile" not in state_response["data"]
    assert state_response["data"]["isStreaming"] is False


def test_rpc_mode_get_state_fills_stable_defaults_for_partial_state() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    class PartialStateSession(FakeSession):
        def __init__(self) -> None:
            super().__init__(session_id="session-a", cwd="/tmp/project")
            self.agent = object()

        def get_state(self):
            return SimpleNamespace(model_selection=None)

        @property
        def auto_compaction_enabled(self) -> None:
            return None

    session = PartialStateSession()
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    state = _parse_jsonl(stdout)[0]["data"]
    assert state["model"] is None
    assert state["thinkingLevel"] == "off"
    assert state["isStreaming"] is False
    assert state["isCompacting"] is False
    assert state["steeringMode"] == "one-at-a-time"
    assert state["followUpMode"] == "one-at-a-time"
    assert state["autoCompactionEnabled"] is False
    assert state["messageCount"] == 0
    assert state["pendingMessageCount"] == 0


def test_rpc_mode_get_state_tolerates_invalid_state_attributes() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    class _Unprintable:
        def __init__(self, label: str) -> None:
            self.label = label

        def __str__(self) -> str:
            raise RuntimeError(f"cannot stringify {self.label}")

    class BrokenSession:
        def __init__(self) -> None:
            self.session_id = _Unprintable("session-id")
            self.session_name = None
            self.session_file = None
            self.agent = SimpleNamespace(steering_mode="unknown", follow_up_mode=None)

        def get_state(self):
            class BrokenState:
                @property
                def steering(self):
                    raise RuntimeError("broken steering")

                @property
                def follow_up(self):
                    raise RuntimeError("broken follow-up")

                @property
                def run(self):
                    raise RuntimeError("broken run")

                @property
                def thinking_level(self):
                    raise RuntimeError("broken thinking level")

                @property
                def is_compacting(self):
                    raise RuntimeError("broken is_compacting")

            return BrokenState()

        def get_session_context(self) -> object:
            raise RuntimeError("broken session context")

        @property
        def auto_compaction_enabled(self):
            raise RuntimeError("broken auto compaction")

        def subscribe(self, _listener):
            def unsubscribe() -> None:
                return None

            return unsubscribe

    session = BrokenSession()
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    state = _parse_jsonl(stdout)[0]["data"]
    assert isinstance(state["sessionId"], str)
    assert "sessionName" not in state
    assert "sessionFile" not in state
    assert state["model"] is None
    assert state["isStreaming"] is False
    assert state["isCompacting"] is False
    assert state["steeringMode"] == "one-at-a-time"
    assert state["followUpMode"] == "one-at-a-time"
    assert state["autoCompactionEnabled"] is False
    assert state["messageCount"] == 0
    assert state["pendingMessageCount"] == 0


def test_rpc_mode_get_state_tolerates_broken_model_selection() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    class BrokenSelectionSession(FakeSession):
        def get_state(self):
            return SimpleNamespace(
                model_selection=object(), run=SimpleNamespace(status="running")
            )

    session = BrokenSelectionSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout)[0]["data"]["model"] is None
    assert _parse_jsonl(stdout)[0]["data"]["isStreaming"] is True


def test_rpc_mode_get_state_tolerates_broken_model_projection() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    class BrokenModel:
        @property
        def provider(self):
            raise RuntimeError("broken provider")

        @property
        def id(self):
            return "alpha"

    class BrokenModelSession:
        def __init__(self) -> None:
            self.session_id = "session-a"
            self.agent = SimpleNamespace(state=SimpleNamespace(model=BrokenModel()))
            self.auto_compaction_enabled = None

        def subscribe(self, _listener):
            def unsubscribe() -> None:
                return None

            return unsubscribe

        def get_session_context(self):
            return SimpleNamespace(messages=[])

        def get_state(self):
            return SimpleNamespace(
                model_selection=None, run=SimpleNamespace(status="idle")
            )

    session = BrokenModelSession()
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    state = _parse_jsonl(stdout)[0]["data"]
    assert state["model"] is None
    assert state["sessionId"] == "session-a"


def test_rpc_mode_get_state_model_uses_id_as_name_and_omits_unknown_cost() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.model_registry = FakeModelRegistry(
        resolved_models={
            ("faux", "alpha"): Model(
                id="alpha",
                provider="faux",
                endpoint="coding",
                capabilities=Capabilities(
                    input=("text",),
                    context_window=100_000,
                    max_tokens=4_096,
                    reasoning=False,
                ),
            )
        },
        endpoints={
            ("faux", "coding"): Endpoint(
                id="coding",
                api="openai-completions",
                provider="faux",
                base_url="https://api.faux.test/v1",
            )
        },
    )
    asyncio.run(session.set_model(ModelSelection(provider="faux", model_id="alpha")))
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    model = _parse_jsonl(stdout)[0]["data"]["model"]
    assert model == {
        "provider": "faux",
        "id": "alpha",
        "name": "alpha",
        "api": "openai-completions",
        "baseUrl": "https://api.faux.test/v1",
        "input": ["text"],
        "contextWindow": 100_000,
        "maxTokens": 4_096,
        "reasoning": False,
    }


def test_rpc_mode_get_state_model_omits_partial_unknown_cost() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.model_registry = FakeModelRegistry(
        resolved_models={
            ("openrouter", "auto"): Model(
                id="auto",
                provider="openrouter",
                endpoint="anthropic-messages",
                capabilities=Capabilities(input=("text",), context_window=100_000),
                pricing=Pricing(input=None, output=None, cache_read=0, cache_write=0),
            )
        },
        endpoints={
            ("openrouter", "anthropic-messages"): Endpoint(
                id="anthropic-messages",
                api="anthropic-messages",
                provider="openrouter",
            )
        },
    )
    asyncio.run(
        session.set_model(ModelSelection(provider="openrouter", model_id="auto"))
    )
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    model = _parse_jsonl(stdout)[0]["data"]["model"]
    assert "cost" not in model


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_rpc_mode_model_cost_omits_invalid_numeric_values(value: float) -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    mode = RpcMode(runtime=FakeRuntime(session), stdin=StringIO(), stdout=StringIO())

    cost = mode._serialize_model_cost(
        SimpleNamespace(input=1.0, output=value, cache_read=0.0, cache_write=0.0)
    )

    assert cost is None


@pytest.mark.parametrize(
    ("command", "payload", "runtime_attr"),
    [
        (
            "new_session",
            {"cwd": "/tmp/project-b", "parentSession": "parent-1"},
            "new_session_calls",
        ),
        ("switch_session", {"sessionId": "session-b"}, "switch_session_calls"),
        ("fork", {"entryId": "entry-42"}, "fork_session_calls"),
    ],
)
def test_rpc_mode_rebinds_runtime_sessions(
    command: str, payload: dict[str, object], runtime_attr: str
) -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    current = FakeSession(session_id="session-a", cwd="/tmp/project-a")
    next_session = FakeSession(
        session_id="session-b",
        cwd="/tmp/project-b",
        event_message=_assistant_message("from-b"),
    )
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "lifecycle", "type": command, **payload}),
                json.dumps({"id": "prompt", "type": "prompt", "message": "hello"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert next_session.prompt_calls == [("hello", None)]
    assert getattr(runtime, runtime_attr)

    lines = _parse_jsonl(stdout)
    lifecycle = lines[0]
    assert lifecycle["type"] == "response"
    assert lifecycle["command"] == command
    assert lifecycle["data"]["cancelled"] is False
    if command == "fork":
        assert lifecycle["data"]["text"] is None
    else:
        assert lifecycle["data"] == {"cancelled": False}
    assert lines[1] == {
        "id": "prompt",
        "type": "response",
        "command": "prompt",
        "success": True,
    }
    assert lines[2]["type"] == "message_end"


def test_rpc_mode_switch_session_accepts_session_path_alias() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    current = FakeSession(session_id="session-a", cwd="/tmp/project-a")
    next_session = FakeSession(session_id="session-b", cwd="/tmp/project-b")
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdin = StringIO(
        json.dumps(
            {"id": "switch", "type": "switch_session", "sessionPath": "/tmp/s-b.jsonl"}
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert runtime.switch_session_calls == ["/tmp/s-b.jsonl"]
    assert _parse_jsonl(stdout)[0]["data"] == {"cancelled": False}


def test_rpc_mode_fork_response_includes_selected_user_text() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    current = FakeSession(session_id="session-a", cwd="/tmp/project-a")
    current.session_manager.set_entry(
        "entry-42",
        _message_record("entry-42", _user_message("selected text")),
    )
    next_session = FakeSession(session_id="session-b", cwd="/tmp/project-b")
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdin = StringIO(
        json.dumps({"id": "fork", "type": "fork", "entryId": "entry-42"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout)[0]["data"] == {
        "cancelled": False,
        "text": "selected text",
    }
    assert runtime.fork_session_operation_calls == [("entry-42", "before")]


def test_rpc_mode_fork_accepts_at_position() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    current = FakeSession(session_id="session-a", cwd="/tmp/project-a")
    current.session_manager.set_entry(
        "entry-42",
        _message_record("entry-42", _user_message("selected text")),
    )
    next_session = FakeSession(session_id="session-b", cwd="/tmp/project-b")
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdin = StringIO(
        json.dumps(
            {"id": "fork", "type": "fork", "entryId": "entry-42", "position": "at"}
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout)[0]["data"] == {"cancelled": False, "text": None}
    assert runtime.fork_session_operation_calls == [("entry-42", "at")]


@pytest.mark.parametrize(
    ("command", "payload", "runtime_attr"),
    [
        (
            "new_session",
            {"cwd": "/tmp/project-b", "parentSession": "parent-1"},
            "new_session_calls",
        ),
        ("switch_session", {"sessionPath": "/tmp/s-b.jsonl"}, "switch_session_calls"),
        ("fork", {"entryId": "leaf-1"}, "fork_session_calls"),
        ("clone", {}, "fork_session_calls"),
    ],
)
def test_rpc_mode_lifecycle_commands_do_not_wait_for_active_prompt(
    command: str,
    payload: dict[str, object],
    runtime_attr: str,
) -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    current = FakeSession(session_id="session-a", cwd="/tmp/project-a")
    current._prompt_started = asyncio.Event()
    current._prompt_release = asyncio.Event()
    next_session = FakeSession(session_id="session-b", cwd="/tmp/project-b")
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(), stdout=stdout)
        await mode.submit_input(
            json.dumps({"id": "p1", "type": "prompt", "message": "start"})
        )
        await current._prompt_started.wait()
        await mode.submit_input(
            json.dumps({"id": "lifecycle", "type": command, **payload})
        )
        await mode.submit_input(
            json.dumps({"id": "p2", "type": "prompt", "message": "after switch"})
        )
        current._prompt_release.set()
        await mode._drain_background_tasks()

    asyncio.run(scenario())

    assert getattr(runtime, runtime_attr)
    assert next_session.prompt_calls == [("after switch", None)]
    lines = _parse_jsonl(stdout)
    lifecycle_response = next(line for line in lines if line.get("id") == "lifecycle")
    assert lifecycle_response["type"] == "response"
    assert lifecycle_response["command"] == command
    assert lifecycle_response["success"] is True
    assert lifecycle_response["data"]["cancelled"] is False
    assert not any(
        isinstance(line.get("error"), str) and "active prompt" in line["error"]
        for line in lines
        if line.get("type") == "response"
    )


def test_rpc_mode_compact_command_does_not_wait_for_active_prompt() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session._prompt_started = asyncio.Event()
    session._prompt_release = asyncio.Event()
    runtime = FakeRuntime(session)
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(), stdout=stdout)
        await mode.submit_input(
            json.dumps({"id": "p1", "type": "prompt", "message": "start"})
        )
        await session._prompt_started.wait()
        await mode.submit_input(json.dumps({"id": "compact", "type": "compact"}))
        session._prompt_release.set()
        await mode._drain_background_tasks()

    asyncio.run(scenario())

    assert session.compact_calls == [None]
    compact_response = next(
        line for line in _parse_jsonl(stdout) if line.get("id") == "compact"
    )
    assert compact_response["type"] == "response"
    assert compact_response["command"] == "compact"
    assert compact_response["success"] is True


def test_rpc_mode_prompt_streaming_behavior_uses_prompt_pipeline_while_active() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    image = {"type": "image", "data": "abc123", "mimeType": "image/png"}
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session._prompt_started = asyncio.Event()
    session._prompt_release = asyncio.Event()
    runtime = FakeRuntime(session)
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(), stdout=stdout)
        await mode.submit_input(
            json.dumps({"id": "p1", "type": "prompt", "message": "hello"})
        )
        await session._prompt_started.wait()
        await mode.submit_input(
            json.dumps(
                {
                    "id": "p2",
                    "type": "prompt",
                    "message": "queued",
                    "images": [image],
                    "streamingBehavior": "followUp",
                }
            )
        )
        session._prompt_release.set()
        await mode._drain_background_tasks()

    asyncio.run(scenario())

    assert session.prompt_calls == [("hello", None), ("queued", [image])]
    assert session.prompt_kwargs[1]["source"] == "rpc"
    assert session.prompt_kwargs[1]["streaming_behavior"] == "followUp"
    assert session.follow_up_calls == [("queued", [image])]
    prompt_responses = [
        line
        for line in _parse_jsonl(stdout)
        if line.get("type") == "response" and line.get("command") == "prompt"
    ]
    assert {line.get("id") for line in prompt_responses} == {"p1", "p2"}
    assert all(line["success"] is True for line in prompt_responses)


def test_rpc_mode_prompt_returns_after_preflight_before_prompt_finishes() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session._prompt_started = asyncio.Event()
    session._prompt_release = asyncio.Event()
    runtime = FakeRuntime(session)
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(), stdout=stdout)
        await mode.submit_input(
            json.dumps({"id": "p1", "type": "prompt", "message": "hello"})
        )
        await session._prompt_started.wait()
        await asyncio.sleep(0)
        assert _parse_jsonl(stdout) == [
            {"id": "p1", "type": "response", "command": "prompt", "success": True}
        ]
        session._prompt_release.set()
        await mode._drain_background_tasks()

    asyncio.run(scenario())

    assert session.prompt_calls == [("hello", None)]
    assert session.wait_calls == 1


def test_rpc_mode_applies_control_commands_to_active_session() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.model_registry = FakeModelRegistry(
        resolved_models={
            ("faux", "beta"): Model(
                id="beta",
                provider="faux",
                endpoint="coding",
                name="Faux Beta",
                capabilities=Capabilities(
                    input=("text",),
                    context_window=256_000,
                    max_tokens=12_288,
                    reasoning=True,
                ),
                pricing=Pricing(input=3, output=4, cache_read=0.3, cache_write=0.4),
                adapter=OpenAICompletionsConfig(reasoning_effort=True),
            )
        },
        endpoints={
            ("faux", "coding"): Endpoint(
                id="coding",
                api="openai-completions",
                provider="faux",
                base_url="https://api.faux.test/v1",
            )
        },
    )
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "steer", "type": "steer", "message": "watch this"}),
                json.dumps(
                    {"id": "follow", "type": "follow_up", "message": "continue"}
                ),
                json.dumps({"id": "abort", "type": "abort"}),
                json.dumps(
                    {
                        "id": "model",
                        "type": "set_model",
                        "provider": "faux",
                        "modelId": "beta",
                    }
                ),
                json.dumps(
                    {
                        "id": "tools",
                        "type": "set_active_tools",
                        "toolNames": ["bash", "read"],
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.steer_calls == [("watch this", None)]
    assert session.follow_up_calls == [("continue", None)]
    assert session.abort_calls == 1
    assert session.set_model_calls == [ModelSelection(provider="faux", model_id="beta")]
    assert session.set_active_tools_calls == [["bash", "read"]]

    lines = _parse_jsonl(stdout)
    assert lines[3] == {
        "id": "model",
        "type": "response",
        "command": "set_model",
        "success": True,
        "data": {
            "provider": "faux",
            "id": "beta",
            "name": "Faux Beta",
            "api": "openai-completions",
            "baseUrl": "https://api.faux.test/v1",
            "input": ["text"],
            "contextWindow": 256_000,
            "maxTokens": 12_288,
            "reasoning": True,
            "cost": {
                "input": 3,
                "output": 4,
                "cacheRead": 0.3,
                "cacheWrite": 0.4,
            },
        },
    }
    commands = [line["command"] for line in lines]
    assert commands == ["steer", "follow_up", "abort", "set_model", "set_active_tools"]


def test_rpc_mode_set_model_rejects_models_outside_available_list() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.model_registry = FakeModelRegistry(
        [ModelSelection(provider="faux", model_id="alpha")]
    )
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps(
            {
                "id": "model",
                "type": "set_model",
                "provider": "faux",
                "modelId": "missing",
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_model_calls == []
    assert _parse_jsonl(stdout) == [
        {
            "id": "model",
            "type": "response",
            "command": "set_model",
            "success": False,
            "error": "Model not found: faux/missing",
        }
    ]


def test_rpc_mode_passes_images_to_steer_and_follow_up_commands() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    image = {"type": "image", "data": "abc123", "mimeType": "image/png"}
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "steer",
                        "type": "steer",
                        "message": "watch",
                        "images": [image],
                    }
                ),
                json.dumps(
                    {
                        "id": "follow",
                        "type": "follow_up",
                        "message": "later",
                        "images": [image],
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.steer_calls == [("watch", [image])]
    assert session.follow_up_calls == [("later", [image])]
    assert _parse_jsonl(stdout) == [
        {"id": "steer", "type": "response", "command": "steer", "success": True},
        {"id": "follow", "type": "response", "command": "follow_up", "success": True},
    ]


def test_rpc_mode_supports_thinking_stats_retry_compact_and_export_commands() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(
        session_id="session-a", session_name="Alpha", cwd="/tmp/project"
    )
    asyncio.run(session.set_active_tools(["bash"]))
    asyncio.run(session.set_model(ModelSelection(provider="faux", model_id="alpha")))
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {"id": "think", "type": "set_thinking_level", "level": "high"}
                ),
                json.dumps({"id": "stats", "type": "get_session_stats"}),
                json.dumps(
                    {"id": "retry-on", "type": "set_auto_retry", "enabled": False}
                ),
                json.dumps({"id": "retry-off", "type": "abort_retry"}),
                json.dumps({"id": "compact", "type": "compact"}),
                json.dumps(
                    {
                        "id": "export",
                        "type": "export_html",
                        "outputPath": "/tmp/exported.html",
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_thinking_level_calls == ["high"]
    assert session.set_auto_retry_calls == [False]
    assert session.abort_retry_calls == 1
    assert session.compact_calls == [None]
    assert session.export_to_html_calls == ["/tmp/exported.html"]

    lines = _parse_jsonl(stdout)
    assert lines[0]["command"] == "set_thinking_level"
    assert lines[0] == {
        "id": "think",
        "type": "response",
        "command": "set_thinking_level",
        "success": True,
    }

    assert lines[1]["command"] == "get_session_stats"
    assert lines[1]["data"]["sessionId"] == "session-a"
    assert lines[1]["data"]["lastModelSelection"] == {
        "provider": "faux",
        "modelId": "alpha",
    }
    assert lines[1]["data"]["contextUsage"]["estimatedContextTokens"] == 123

    assert lines[2] == {
        "id": "retry-on",
        "type": "response",
        "command": "set_auto_retry",
        "success": True,
    }
    assert lines[3] == {
        "id": "retry-off",
        "type": "response",
        "command": "abort_retry",
        "success": True,
    }

    assert lines[4]["command"] == "compact"
    assert lines[4]["data"] == {
        "summary": "compacted",
        "firstKeptEntryId": "entry-1",
        "tokensBefore": 42,
        "details": {"preserved": 3},
    }

    assert lines[5] == {
        "id": "export",
        "type": "response",
        "command": "export_html",
        "success": True,
        "data": {"path": "/tmp/exported.html"},
    }


def test_rpc_mode_passes_custom_instructions_to_compact_command() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "camel",
                        "type": "compact",
                        "customInstructions": "keep API details",
                    }
                ),
                json.dumps(
                    {
                        "id": "snake",
                        "type": "compact",
                        "custom_instructions": "keep tests",
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.compact_calls == ["keep API details", "keep tests"]
    assert [line["command"] for line in _parse_jsonl(stdout)] == ["compact", "compact"]


def test_rpc_mode_supports_queue_model_name_and_command_queries() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    assistant = _assistant_message("latest answer")
    session = FakeSession(
        session_id="session-a",
        session_name="Alpha",
        cwd="/tmp/project",
        messages=[assistant],
    )
    session.model_registry = FakeModelRegistry(
        [
            ModelSelection(provider="faux", model_id="alpha"),
            ModelSelection(provider="openai", model_id="gpt-5"),
        ],
        resolved_models={
            ("faux", "alpha"): Model(
                id="alpha",
                provider="faux",
                endpoint="coding",
                name="Faux Alpha",
                capabilities=Capabilities(
                    input=("text",),
                    context_window=128_000,
                    max_tokens=8_192,
                    reasoning=False,
                ),
                pricing=Pricing(input=1, output=2, cache_read=0.1, cache_write=0.2),
                adapter=OpenAICompletionsConfig(reasoning_effort=False),
            ),
            ("openai", "gpt-5"): Model(
                id="gpt-5",
                provider="openai",
                endpoint="coding",
                name="GPT-5",
                capabilities=Capabilities(
                    input=("text", "image"),
                    context_window=400_000,
                    max_tokens=16_384,
                    reasoning=True,
                ),
                pricing=Pricing(input=5, output=15, cache_read=0.5, cache_write=0.8),
                adapter=OpenAICompletionsConfig(reasoning_effort=True),
            ),
        },
        endpoints={
            ("faux", "coding"): Endpoint(
                id="coding",
                api="openai-completions",
                provider="faux",
                base_url="https://api.faux.test/v1",
            ),
            ("openai", "coding"): Endpoint(
                id="coding",
                api="openai-responses",
                provider="openai",
                base_url="https://api.openai.test/v1",
            ),
        },
    )
    session.resource_bundle = ResourceBundle(
        cwd=Path("/tmp/project"),
        prompts=[
            PromptFragmentDescriptor(
                name="review",
                source_path=Path("/tmp/project/prompts/review.md"),
                text="Review prompt",
            )
        ],
        skills=[
            SkillDescriptor(
                name="debug",
                source_path=Path("/tmp/project/skills/debug/SKILL.md"),
                content="# Debug",
            )
        ],
    )
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {"id": "steering-mode", "type": "set_steering_mode", "mode": "all"}
                ),
                json.dumps(
                    {"id": "follow-mode", "type": "set_follow_up_mode", "mode": "all"}
                ),
                json.dumps({"id": "models", "type": "get_available_models"}),
                json.dumps(
                    {"id": "rename", "type": "set_session_name", "name": "Renamed"}
                ),
                json.dumps({"id": "last", "type": "get_last_assistant_text"}),
                json.dumps({"id": "commands", "type": "get_commands"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_steering_mode_calls == ["all"]
    assert session.set_follow_up_mode_calls == ["all"]
    assert session.set_session_name_calls == ["Renamed"]
    assert session.session_manager.session_info_calls == ["Renamed"]

    lines = _parse_jsonl(stdout)
    assert lines[0] == {
        "id": "steering-mode",
        "type": "response",
        "command": "set_steering_mode",
        "success": True,
    }
    assert lines[1] == {
        "id": "follow-mode",
        "type": "response",
        "command": "set_follow_up_mode",
        "success": True,
    }
    assert lines[2] == {
        "id": "models",
        "type": "response",
        "command": "get_available_models",
        "success": True,
        "data": {
            "models": [
                {
                    "provider": "faux",
                    "id": "alpha",
                    "name": "Faux Alpha",
                    "api": "openai-completions",
                    "baseUrl": "https://api.faux.test/v1",
                    "input": ["text"],
                    "contextWindow": 128_000,
                    "maxTokens": 8_192,
                    "reasoning": False,
                    "cost": {
                        "input": 1,
                        "output": 2,
                        "cacheRead": 0.1,
                        "cacheWrite": 0.2,
                    },
                },
                {
                    "provider": "openai",
                    "id": "gpt-5",
                    "name": "GPT-5",
                    "api": "openai-responses",
                    "baseUrl": "https://api.openai.test/v1",
                    "input": ["text", "image"],
                    "contextWindow": 400_000,
                    "maxTokens": 16_384,
                    "reasoning": True,
                    "cost": {
                        "input": 5,
                        "output": 15,
                        "cacheRead": 0.5,
                        "cacheWrite": 0.8,
                    },
                },
            ]
        },
    }
    assert lines[3] == {
        "id": "rename",
        "type": "response",
        "command": "set_session_name",
        "success": True,
    }
    assert lines[4] == {
        "id": "last",
        "type": "response",
        "command": "get_last_assistant_text",
        "success": True,
        "data": {"text": "latest answer"},
    }
    assert lines[5] == {
        "id": "commands",
        "type": "response",
        "command": "get_commands",
        "success": True,
        "data": {
            "commands": [
                {
                    "name": "/review",
                    "description": None,
                    "source": "prompt",
                    "sourceInfo": {
                        "path": "/tmp/project/prompts/review.md",
                        "source": "filesystem",
                        "scope": "project",
                        "origin": "top-level",
                        "baseDir": "/tmp/project/prompts",
                    },
                },
                {
                    "name": "/skill:debug",
                    "description": None,
                    "source": "skill",
                    "sourceInfo": {
                        "path": "/tmp/project/skills/debug/SKILL.md",
                        "source": "filesystem",
                        "scope": "project",
                        "origin": "top-level",
                        "baseDir": "/tmp/project/skills/debug",
                    },
                },
            ]
        },
    }


def test_rpc_mode_set_session_name_trims_and_rejects_blank_names() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "blank", "type": "set_session_name", "name": "   "}),
                json.dumps(
                    {"id": "trimmed", "type": "set_session_name", "name": "  Renamed  "}
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_session_name_calls == ["Renamed"]
    assert _parse_jsonl(stdout) == [
        {
            "id": "blank",
            "type": "response",
            "command": "set_session_name",
            "success": False,
            "error": "Session name cannot be empty",
        },
        {
            "id": "trimmed",
            "type": "response",
            "command": "set_session_name",
            "success": True,
        },
    ]


def test_rpc_mode_get_commands_includes_extension_prompt_and_skill_entries() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.command_entries = [
        {
            "name": "deploy",
            "description": "Deploy the project",
            "source": "extension",
            "source_info": {"path": "/tmp/project/extensions/deploy-ext.py"},
        },
        {
            "name": "plan",
            "description": "Use a planning workflow before editing.",
            "source": "prompt",
            "source_info": {"path": "/tmp/project/prompts/plan.md"},
        },
        {
            "name": "skill:debugging",
            "description": "Check the failing path first.",
            "source": "skill",
            "source_info": {"path": "/tmp/project/skills/debugging/SKILL.md"},
        },
    ]
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "commands", "type": "get_commands"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert lines == [
        {
            "id": "commands",
            "type": "response",
            "command": "get_commands",
            "success": True,
            "data": {
                "commands": [
                    {
                        "name": "deploy",
                        "description": "Deploy the project",
                        "source": "extension",
                        "sourceInfo": {
                            "path": "/tmp/project/extensions/deploy-ext.py",
                            "source": "filesystem",
                            "scope": "project",
                            "origin": "top-level",
                            "baseDir": "/tmp/project/extensions",
                        },
                    },
                    {
                        "name": "plan",
                        "description": "Use a planning workflow before editing.",
                        "source": "prompt",
                        "sourceInfo": {
                            "path": "/tmp/project/prompts/plan.md",
                            "source": "filesystem",
                            "scope": "project",
                            "origin": "top-level",
                            "baseDir": "/tmp/project/prompts",
                        },
                    },
                    {
                        "name": "skill:debugging",
                        "description": "Check the failing path first.",
                        "source": "skill",
                        "sourceInfo": {
                            "path": "/tmp/project/skills/debugging/SKILL.md",
                            "source": "filesystem",
                            "scope": "project",
                            "origin": "top-level",
                            "baseDir": "/tmp/project/skills/debugging",
                        },
                    },
                ]
            },
        }
    ]


def test_rpc_mode_get_diagnostics_and_last_error_report() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    warning = DiagnosticRecord(
        type="warning",
        code="model_auth_unresolved",
        message="Provider demo has no configured API key.",
        phase="startup",
        source="model",
        timestamp="2026-05-01T00:00:00Z",
        session_id="session-a",
        source_path=Path("/tmp/project/.loushang/settings.json"),
        details={"provider": "demo"},
        fingerprint="fp-warning",
        occurrence_count=2,
    )
    error = DiagnosticRecord(
        type="error",
        code="assistant_response_error",
        message="provider failed",
        phase="runtime",
        source="provider",
        timestamp="2026-05-01T00:01:00Z",
        session_id="session-a",
        entry_id="entry-1",
        details={"retry": True},
        fingerprint="fp-error",
    )
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.diagnostics = [warning, error]
    session.error_report = ErrorReport(primary=error, related=(warning,))
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {"id": "diagnostics", "type": "get_diagnostics", "limit": 1}
                ),
                json.dumps({"id": "report", "type": "get_last_error_report"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert lines[0] == {
        "id": "diagnostics",
        "type": "response",
        "command": "get_diagnostics",
        "success": True,
        "data": {
            "diagnostics": [
                {
                    "type": "error",
                    "code": "assistant_response_error",
                    "message": "provider failed",
                    "phase": "runtime",
                    "source": "provider",
                    "timestamp": "2026-05-01T00:01:00Z",
                    "details": {"retry": True},
                    "occurrenceCount": 1,
                    "sessionId": "session-a",
                    "entryId": "entry-1",
                    "fingerprint": "fp-error",
                }
            ]
        },
    }
    assert lines[1]["id"] == "report"
    assert lines[1]["success"] is True
    report = lines[1]["data"]["report"]
    assert report["primary"]["code"] == "assistant_response_error"
    assert report["related"][0]["code"] == "model_auth_unresolved"
    assert report["related"][0]["occurrenceCount"] == 2


def test_rpc_mode_get_packages_projects_remote_lifecycle_state() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.packages = [
        {
            "name": "review-pack",
            "kind": "remote_plugin",
            "scope": "project",
            "version": "",
            "source": "https://packages.example.invalid/review-pack.git",
            "path": "",
            "enabled": False,
            "prompts": 0,
            "skills": 0,
            "extensions": 0,
            "themes": 0,
            "diagnostics": 0,
            "lifecycle": "remote_registered",
            "security": "allowed",
            "description": "",
        }
    ]
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "packages", "type": "get_packages"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.get_packages_calls == [None]
    assert response == {
        "id": "packages",
        "type": "response",
        "command": "get_packages",
        "success": True,
        "data": {"packages": session.packages},
    }


def test_rpc_mode_materialize_package_uses_runtime_facade() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    source = "https://packages.example.invalid/review-pack.git"
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps(
            {"id": "materialize", "type": "materialize_package", "source": source}
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.materialize_package_calls == [source]
    assert response == {
        "id": "materialize",
        "type": "response",
        "command": "materialize_package",
        "success": True,
        "data": {
            "record": {
                "source": source,
                "name": "review-pack",
                "lifecycle": "materialization_pending",
                "targetPath": "/tmp/packages/review-pack",
                "errorMessage": None,
            }
        },
    }


def test_rpc_mode_update_package_uses_runtime_facade() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    source = "https://packages.example.invalid/review-pack.git"
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "update", "type": "update_package", "source": source}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.update_package_calls == [source]
    assert response == {
        "id": "update",
        "type": "response",
        "command": "update_package",
        "success": True,
        "data": {
            "record": {
                "source": source,
                "name": "review-pack",
                "lifecycle": "installed",
                "targetPath": "/tmp/packages/review-pack",
                "errorMessage": None,
            }
        },
    }


def test_rpc_mode_remove_package_uses_runtime_facade() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    source = "https://packages.example.invalid/review-pack.git"
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "remove", "type": "remove_package", "source": source}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.remove_package_calls == [source]
    assert response == {
        "id": "remove",
        "type": "response",
        "command": "remove_package",
        "success": True,
        "data": {
            "record": {
                "source": source,
                "name": "review-pack",
                "lifecycle": "remote_registered",
                "targetPath": "/tmp/packages/review-pack",
                "errorMessage": None,
            }
        },
    }


def test_rpc_mode_package_lifecycle_failed_record_returns_error() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    source = "https://packages.example.invalid/review-pack.git"
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)

    async def failed_materialize(source_arg: str) -> dict[str, object]:
        runtime.materialize_package_calls.append(source_arg)
        return {
            "source": source_arg,
            "name": "review-pack",
            "lifecycle": "failed",
            "targetPath": "/tmp/packages/review-pack",
            "errorMessage": "clone failed",
        }

    runtime.materialize_package = failed_materialize  # type: ignore[method-assign]
    stdin = StringIO(
        json.dumps(
            {"id": "materialize", "type": "materialize_package", "source": source}
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    response = _parse_jsonl(stdout)[0]
    assert runtime.materialize_package_calls == [source]
    assert response == {
        "id": "materialize",
        "type": "response",
        "command": "materialize_package",
        "success": False,
        "error": "Failed to materialize package: clone failed",
        "errorCode": "package_materialization_failed",
        "errorInfo": {
            "command": "materialize_package",
            "code": "package_materialization_failed",
            "message": "Failed to materialize package: clone failed",
        },
    }


def test_rpc_mode_high_level_package_manager_commands_use_runtime_facade() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    source = "https://packages.example.invalid/review-pack.git"
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {"id": "install", "type": "install_package", "source": source}
                ),
                json.dumps({"id": "check", "type": "check_package_updates"}),
                json.dumps({"id": "update-all", "type": "update_packages"}),
                json.dumps(
                    {"id": "uninstall", "type": "uninstall_package", "source": source}
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    responses = _parse_jsonl(stdout)
    assert runtime.install_package_calls == [source]
    assert runtime.check_package_updates_calls == 1
    assert runtime.update_packages_calls == 1
    assert runtime.uninstall_package_calls == [source]
    assert [response["command"] for response in responses] == [
        "install_package",
        "check_package_updates",
        "update_packages",
        "uninstall_package",
    ]
    assert responses[1]["data"]["updates"][0]["availableCommit"] == "b"
    assert responses[2]["data"]["records"][0]["lifecycle"] == "installed"


def test_rpc_mode_get_diagnostics_supports_query_filters() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    provider_error = DiagnosticRecord(
        type="error",
        code="assistant_response_error",
        message="provider failed",
        phase="runtime",
        source="provider",
        timestamp="2026-05-01T00:01:00Z",
        session_id="session-a",
        entry_id="entry-a",
        details={},
    )
    session_warning = DiagnosticRecord(
        type="warning",
        code="startup_warning",
        message="heads up",
        phase="startup",
        source="bootstrap",
        timestamp="2026-05-01T00:00:00Z",
        session_id="session-b",
        entry_id="entry-b",
        details={},
    )
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    runtime.diagnostics = [session_warning, provider_error]
    stdin = StringIO(
        json.dumps(
            {
                "id": "diagnostics",
                "type": "get_diagnostics",
                "limit": 5,
                "phase": "runtime",
                "source": "provider",
                "level": "error",
                "sessionId": "session-a",
                "entryId": "entry-a",
                "code": "assistant_response_error",
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert runtime.get_diagnostics_calls == [
        DiagnosticsQuery(
            phase="runtime",
            source="provider",
            level="error",
            session_id="session-a",
            entry_id="entry-a",
            code="assistant_response_error",
            limit=5,
        )
    ]
    response = _parse_jsonl(stdout)[0]
    assert [record["code"] for record in response["data"]["diagnostics"]] == [
        "assistant_response_error"
    ]


def test_rpc_mode_get_session_diagnostics_uses_session_scoped_runtime_query() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    current_session_error = DiagnosticRecord(
        type="error",
        code="current_session_error",
        message="current failed",
        phase="runtime",
        source="session",
        timestamp="2026-05-01T00:01:00Z",
        session_id="session-a",
        entry_id="entry-a",
        details={},
    )
    other_session_error = DiagnosticRecord(
        type="error",
        code="other_session_error",
        message="other failed",
        phase="runtime",
        source="session",
        timestamp="2026-05-01T00:02:00Z",
        session_id="session-b",
        entry_id="entry-b",
        details={},
    )
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    runtime.diagnostics = [other_session_error, current_session_error]
    stdin = StringIO(
        json.dumps(
            {
                "id": "session-diagnostics",
                "type": "get_session_diagnostics",
                "limit": 5,
                "phase": "runtime",
                "source": "session",
                "level": "error",
                "code": "current_session_error",
            }
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert runtime.get_session_diagnostics_calls == [
        DiagnosticsQuery(
            phase="runtime",
            source="session",
            level="error",
            code="current_session_error",
            limit=5,
        )
    ]
    assert runtime.get_diagnostics_calls == []
    response = _parse_jsonl(stdout)[0]
    assert response["command"] == "get_session_diagnostics"
    assert [record["code"] for record in response["data"]["diagnostics"]] == [
        "current_session_error"
    ]


def test_rpc_mode_get_diagnostics_summary_projects_counts() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    provider_error = DiagnosticRecord(
        type="error",
        code="assistant_response_error",
        message="provider failed",
        phase="runtime",
        source="provider",
        timestamp="2026-05-01T00:01:00Z",
        session_id="session-a",
        entry_id="entry-a",
        details={},
        occurrence_count=3,
    )
    startup_warning = DiagnosticRecord(
        type="warning",
        code="startup_warning",
        message="heads up",
        phase="startup",
        source="bootstrap",
        timestamp="2026-05-01T00:00:00Z",
        session_id="session-a",
        details={},
    )
    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    runtime.diagnostics = [startup_warning, provider_error]
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "summary",
                        "type": "get_diagnostics_summary",
                        "sessionId": "session-a",
                    }
                ),
                json.dumps(
                    {"id": "session-summary", "type": "get_session_diagnostics_summary"}
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert runtime.get_diagnostics_summary_calls == [
        DiagnosticsQuery(session_id="session-a")
    ]
    assert runtime.get_session_diagnostics_summary_calls == [DiagnosticsQuery()]
    assert lines[0]["command"] == "get_diagnostics_summary"
    summary = lines[0]["data"]["summary"]
    assert summary["totalCount"] == 4
    assert summary["errorCount"] == 3
    assert summary["warningCount"] == 1
    assert summary["byCode"] == {"startup_warning": 1, "assistant_response_error": 3}
    assert summary["latestError"]["code"] == "assistant_response_error"
    assert lines[1]["command"] == "get_session_diagnostics_summary"
    assert lines[1]["data"]["summary"]["totalCount"] == 4


def test_rpc_mode_get_diagnostics_rejects_invalid_limit() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "diagnostics", "type": "get_diagnostics", "limit": 0}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "diagnostics",
            "type": "response",
            "command": "get_diagnostics",
            "success": False,
            "error": "Diagnostic limit must be a positive integer.",
        }
    ]


def test_rpc_mode_get_commands_prefers_session_command_descriptors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class DescriptorSession(FakeSession):
        def list_commands(self):
            return [
                SessionCommandDescriptor(
                    name="deploy",
                    description="Deploy the project",
                    source="extension",
                    source_info=CommandSourceInfo(
                        path="/tmp/project/extensions/deploy.py",
                        base_dir="/tmp/project/extensions",
                    ),
                )
            ]

    session = DescriptorSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "commands", "type": "get_commands"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "commands",
            "type": "response",
            "command": "get_commands",
            "success": True,
            "data": {
                "commands": [
                    {
                        "name": "deploy",
                        "description": "Deploy the project",
                        "source": "extension",
                        "sourceInfo": {
                            "path": "/tmp/project/extensions/deploy.py",
                            "source": "filesystem",
                            "scope": "project",
                            "origin": "top-level",
                            "baseDir": "/tmp/project/extensions",
                        },
                    }
                ]
            },
        }
    ]


def test_rpc_mode_get_commands_projects_session_command_descriptors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.command_entries = [
        SessionCommandDescriptor(
            name="deploy",
            description="Deploy the project",
            source="extension",
            source_info=CommandSourceInfo(
                path="/tmp/project/extensions/deploy-ext.py",
                base_dir="/tmp/project/extensions",
            ),
        ),
        SessionCommandDescriptor(
            name="plan",
            description="Plan the work.",
            source="prompt",
            source_info=CommandSourceInfo(
                path="/tmp/project/prompts/plan.md", base_dir="/tmp/project/prompts"
            ),
            argument_hint="[topic]",
        ),
        SessionCommandDescriptor(
            name="legacy",
            description=None,
            source="skill",
            source_info=CommandSourceInfo(
                path="/tmp/project/skills/legacy.md", base_dir="/tmp/project/skills"
            ),
        ),
        SessionCommandDescriptor(
            name="metadata",
            description="Uses descriptor metadata.",
            source="extension",
            source_info=CommandSourceInfo(
                path="/tmp/project/extensions/alias-cased.md",
                source="project-metadata",
                scope="user",
                origin="package",
                base_dir="/tmp/explicit-base",
            ),
        ),
    ]
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "commands", "type": "get_commands"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    commands = _parse_jsonl(stdout)[0]["data"]["commands"]
    assert commands == [
        {
            "name": "deploy",
            "description": "Deploy the project",
            "source": "extension",
            "sourceInfo": {
                "path": "/tmp/project/extensions/deploy-ext.py",
                "source": "filesystem",
                "scope": "project",
                "origin": "top-level",
                "baseDir": "/tmp/project/extensions",
            },
        },
        {
            "name": "plan",
            "description": "Plan the work.",
            "source": "prompt",
            "argumentHint": "[topic]",
            "sourceInfo": {
                "path": "/tmp/project/prompts/plan.md",
                "source": "filesystem",
                "scope": "project",
                "origin": "top-level",
                "baseDir": "/tmp/project/prompts",
            },
        },
        {
            "name": "legacy",
            "description": None,
            "source": "skill",
            "sourceInfo": {
                "path": "/tmp/project/skills/legacy.md",
                "source": "filesystem",
                "scope": "project",
                "origin": "top-level",
                "baseDir": "/tmp/project/skills",
            },
        },
        {
            "name": "metadata",
            "description": "Uses descriptor metadata.",
            "source": "extension",
            "sourceInfo": {
                "path": "/tmp/project/extensions/alias-cased.md",
                "source": "project-metadata",
                "scope": "user",
                "origin": "package",
                "baseDir": "/tmp/explicit-base",
            },
        },
    ]


def test_rpc_mode_get_command_completions_returns_command_and_argument_suggestions() -> (
    None
):
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class CompletionSession(FakeSession):
        async def get_command_argument_completions(
            self, invocation_name: str, prefix: str
        ) -> list[object]:
            assert (invocation_name, prefix) == ("deploy", "pr")
            return [{"value": "prod", "label": "Production"}]

    session = CompletionSession(session_id="session-a", cwd="/tmp/project")
    session.command_entries = [
        {
            "name": "deploy",
            "description": "Deploy the project",
            "source": "extension",
            "source_info": {"path": "/tmp/project/extensions/deploy-ext.py"},
        },
        {
            "name": "debug",
            "description": "Debug",
            "source": "skill",
            "source_info": {"path": "/tmp/project/skills/debug/SKILL.md"},
        },
    ]
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {"id": "names", "type": "get_command_completions", "prefix": "/dep"}
                ),
                json.dumps(
                    {
                        "id": "args",
                        "type": "get_command_completions",
                        "command": "deploy",
                        "prefix": "pr",
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert await mode.run() == 0

    asyncio.run(scenario())

    names, args = _parse_jsonl(stdout)
    assert names["data"]["completions"] == [
        {
            "value": "/deploy",
            "label": "/deploy",
            "description": "Deploy the project",
            "source": "extension",
            "kind": "command",
        }
    ]
    assert args["data"]["completions"] == [{"value": "prod", "label": "Production"}]


def test_rpc_mode_query_command_errors_stay_in_response_envelopes() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenQuerySession(FakeSession):
        def get_available_models(self) -> list[ModelSelection]:
            raise RuntimeError("model registry failed")

        def list_commands(self) -> list[object]:
            raise RuntimeError("command registry failed")

    session = BrokenQuerySession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "models", "type": "get_available_models"}),
                json.dumps({"id": "commands", "type": "get_commands"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "models",
            "type": "response",
            "command": "get_available_models",
            "success": False,
            "error": "Failed to query model registry: model registry failed",
        },
        {
            "id": "commands",
            "type": "response",
            "command": "get_commands",
            "success": False,
            "error": "Failed to query commands: command registry failed",
        },
    ]


def test_rpc_mode_get_available_models_returns_error_on_invalid_payload() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class InvalidModelSession(FakeSession):
        def get_available_models(self) -> object:
            return {"providers": []}

    session = InvalidModelSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "models", "type": "get_available_models"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "models",
            "type": "response",
            "command": "get_available_models",
            "success": False,
            "error": "Model registry returned an invalid response.",
        },
    ]


def test_rpc_mode_get_available_models_skips_invalid_model_entries() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenModelSession(FakeSession):
        def get_available_models(self):
            return [
                SimpleNamespace(provider="faux", model_id="alpha"),
                object(),
            ]

    session = BrokenModelSession(session_id="session-a", cwd="/tmp/project")
    session.model_registry = FakeModelRegistry(
        resolved_models={
            ("faux", "alpha"): Model(
                id="alpha",
                provider="faux",
                endpoint="coding",
                name="Alpha",
                capabilities=Capabilities(
                    input=("text",),
                    context_window=128_000,
                    max_tokens=8_192,
                    reasoning=True,
                ),
            )
        },
        endpoints={
            ("faux", "coding"): Endpoint(
                id="coding",
                api="openai-completions",
                provider="faux",
                base_url="https://api.faux.test/v1",
            )
        },
    )
    runtime = FakeRuntime(session)
    stdout = StringIO()
    stderr = StringIO()

    async def scenario() -> None:
        mode = RpcMode(
            runtime=runtime,
            stdin=StringIO(
                json.dumps({"id": "models", "type": "get_available_models"}) + "\n"
            ),
            stdout=stdout,
            stderr=stderr,
        )
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert lines == [
        {
            "id": "models",
            "type": "response",
            "command": "get_available_models",
            "success": True,
            "data": {
                "models": [
                    {
                        "provider": "faux",
                        "id": "alpha",
                        "name": "Alpha",
                        "api": "openai-completions",
                        "baseUrl": "https://api.faux.test/v1",
                        "input": ["text"],
                        "contextWindow": 128000,
                        "maxTokens": 8192,
                        "reasoning": True,
                    },
                ],
            },
        }
    ]


def test_rpc_mode_get_commands_returns_error_on_invalid_payload() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class InvalidCommandSession(FakeSession):
        def list_commands(self) -> object:
            return {"commands": ["/bad"]}

    session = InvalidCommandSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "commands", "type": "get_commands"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "commands",
            "type": "response",
            "command": "get_commands",
            "success": False,
            "error": "Command registry returned an invalid response.",
        },
    ]


def test_rpc_mode_get_commands_skips_entries_without_valid_names() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.command_entries = [
        {
            "name": "deploy",
            "description": "Good command",
            "source": "extension",
            "source_info": {"path": "/tmp/project/extensions/deploy.py"},
        },
        {"name": "", "description": "Missing name"},
        {"description": "No name"},
        {"name": 123, "description": "Invalid name"},
        {
            "name": "plan",
            "description": "Another good command",
            "source": "prompt",
            "source_info": {"path": "/tmp/project/prompts/plan.md"},
        },
    ]
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "commands", "type": "get_commands"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    commands = _parse_jsonl(stdout)[0]["data"]["commands"]
    assert commands == [
        {
            "name": "deploy",
            "description": "Good command",
            "source": "extension",
            "sourceInfo": {
                "path": "/tmp/project/extensions/deploy.py",
                "source": "filesystem",
                "scope": "project",
                "origin": "top-level",
                "baseDir": "/tmp/project/extensions",
            },
        },
        {
            "name": "plan",
            "description": "Another good command",
            "source": "prompt",
            "sourceInfo": {
                "path": "/tmp/project/prompts/plan.md",
                "source": "filesystem",
                "scope": "project",
                "origin": "top-level",
                "baseDir": "/tmp/project/prompts",
            },
        },
    ]


def test_rpc_mode_get_messages_skips_invalid_entries_when_serialization_fails() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenMessageSession(FakeSession):
        def get_session_context(self):
            return SimpleNamespace(
                messages=[
                    _assistant_message("ok"),
                    object(),
                    _user_message("follow"),
                ]
            )

    session = BrokenMessageSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "messages", "type": "get_messages"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert lines[0]["type"] == "response"
    assert lines[0]["command"] == "get_messages"
    assert lines[0]["success"] is True
    assert len(lines[0]["data"]["messages"]) == 2
    assert lines[0]["data"]["messages"][0]["role"] == "assistant"
    assert lines[0]["data"]["messages"][1]["role"] == "user"


def test_rpc_mode_get_messages_returns_error_when_session_context_is_invalid() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenMessageGetterSession(FakeSession):
        def get_session_context(
            self,
        ):  # pragma: no cover - defensive path exercised by test
            return object()

    session = BrokenMessageGetterSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "messages", "type": "get_messages"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        # simulate an upstream corruption that bypasses expected list shapes
        mode._get_session_messages = lambda _session: "invalid"
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "messages",
            "type": "response",
            "command": "get_messages",
            "success": False,
            "error": "Message log returned an invalid response.",
        },
    ]


def test_rpc_mode_get_state_returns_error_when_state_serialization_fails() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenStateSession(FakeSession):
        def get_state(self):  # type: ignore[override]
            raise RuntimeError("state unavailable")

    session = BrokenStateSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "state",
            "type": "response",
            "command": "get_state",
            "success": False,
            "error": "Failed to serialize session state.",
        },
    ]


def test_rpc_mode_get_state_uses_standard_session_state() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "state", "type": "get_state"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "state",
            "type": "response",
            "command": "get_state",
            "success": True,
            "data": {
                "sessionId": "session-a",
                "model": None,
                "isStreaming": False,
                "isCompacting": False,
                "steeringMode": "one-at-a-time",
                "followUpMode": "one-at-a-time",
                "autoCompactionEnabled": True,
                "messageCount": 0,
                "pendingMessageCount": 0,
                "thinkingLevel": "off",
                "sessionFile": "/tmp/project/session-a.jsonl",
            },
        },
    ]


def test_rpc_mode_get_session_stats_handles_query_errors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenStatsSession(FakeSession):
        def get_session_stats(self) -> object:
            raise RuntimeError("stats failed")

    session = BrokenStatsSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "stats", "type": "get_session_stats"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "stats",
            "type": "response",
            "command": "get_session_stats",
            "success": False,
            "error": "Failed to query session stats: stats failed",
        },
    ]


def test_rpc_mode_get_session_stats_prefers_public_snake_case_payload() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class SnakeCaseStatsSession(FakeSession):
        def get_session_stats(self) -> dict[str, object]:
            return {"sessionId": self.session_id, "customCounter": 3}

    session = SnakeCaseStatsSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "stats", "type": "get_session_stats"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "stats",
            "type": "response",
            "command": "get_session_stats",
            "success": True,
            "data": {"sessionId": "session-a", "customCounter": 3},
        },
    ]


def test_rpc_mode_get_session_stats_returns_error_when_payload_invalid() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class InvalidStatsSession(FakeSession):
        def get_session_stats(self) -> object:
            return ["invalid"]

    session = InvalidStatsSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "stats", "type": "get_session_stats"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "stats",
            "type": "response",
            "command": "get_session_stats",
            "success": False,
            "error": "Session stats returned an invalid response.",
        },
    ]


def test_rpc_mode_set_model_reports_model_registry_errors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenModelSession(FakeSession):
        def get_available_models(self):
            raise RuntimeError("model registry failed")

    session = BrokenModelSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps(
            {"id": "model", "type": "set_model", "provider": "faux", "modelId": "alpha"}
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "model",
            "type": "response",
            "command": "set_model",
            "success": False,
            "error": "Failed to query model registry: model registry failed",
        }
    ]


def test_rpc_mode_set_model_reports_invalid_model_registry_response_type() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class InvalidTypeSession(FakeSession):
        def get_available_models(self):
            return {"provider": "faux", "modelId": "alpha"}

    session = InvalidTypeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps(
            {"id": "model", "type": "set_model", "provider": "faux", "modelId": "alpha"}
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_model_calls == []
    assert _parse_jsonl(stdout) == [
        {
            "id": "model",
            "type": "response",
            "command": "set_model",
            "success": False,
            "error": "Model registry returned an invalid response.",
        }
    ]


def test_rpc_mode_set_active_tools_reports_setter_errors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenToolsSession(FakeSession):
        async def set_active_tools(self, tool_names: list[str]) -> None:
            raise RuntimeError("tool configuration failed")

    session = BrokenToolsSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "tools", "type": "set_active_tools", "toolNames": ["bash"]})
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "tools",
            "type": "response",
            "command": "set_active_tools",
            "success": False,
            "error": "Failed to set active tools: tool configuration failed",
        }
    ]


def test_rpc_mode_compact_reports_execution_errors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenCompactSession(FakeSession):
        async def compact(self, custom_instructions: str | None = None):
            del custom_instructions
            raise RuntimeError("compact failed")

    session = BrokenCompactSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "compact", "type": "compact"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "compact",
            "type": "response",
            "command": "compact",
            "success": False,
            "error": "Failed to compact session: compact failed",
        }
    ]


def test_rpc_mode_get_fork_messages_returns_error_when_payload_invalid() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class InvalidForkMessagesSession(FakeSession):
        def get_user_messages_for_forking(self) -> object:
            return {"messages": []}

    session = InvalidForkMessagesSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "fork-messages", "type": "get_fork_messages"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "fork-messages",
            "type": "response",
            "command": "get_fork_messages",
            "success": False,
            "error": "Fork messages returned an invalid response.",
        },
    ]


def test_rpc_mode_get_last_assistant_text_handles_extraction_errors() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BrokenLastAssistantTextSession(FakeSession):
        def get_last_assistant_text(self) -> str | None:
            raise RuntimeError("assistant extraction failed")

    session = BrokenLastAssistantTextSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "last", "type": "get_last_assistant_text"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "last",
            "type": "response",
            "command": "get_last_assistant_text",
            "success": False,
            "error": "Failed to read last assistant text: assistant extraction failed",
        },
    ]


def test_rpc_mode_get_last_assistant_text_uses_standard_session_method() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class StandardLastAssistantSession(FakeSession):
        def get_last_assistant_text(self):
            return "latest"

    session = StandardLastAssistantSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "last", "type": "get_last_assistant_text"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout)[0]["data"] == {"text": "latest"}


def test_rpc_mode_supports_cycle_thinking_and_auto_compaction_commands() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.set_thinking_level("low")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "cycle", "type": "cycle_thinking_level"}),
                json.dumps(
                    {
                        "id": "compact-setting",
                        "type": "set_auto_compaction",
                        "enabled": False,
                    }
                ),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_thinking_level_calls == ["low", "medium"]
    assert session.set_auto_compaction_calls == [False]

    lines = _parse_jsonl(stdout)
    assert lines[0] == {
        "id": "cycle",
        "type": "response",
        "command": "cycle_thinking_level",
        "success": True,
        "data": {"level": "medium"},
    }
    assert lines[1] == {
        "id": "compact-setting",
        "type": "response",
        "command": "set_auto_compaction",
        "success": True,
    }


def test_rpc_mode_supports_cycle_model_command() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session.model_registry = FakeModelRegistry(
        [
            ModelSelection(provider="faux", model_id="alpha"),
            ModelSelection(provider="openai", model_id="gpt-5"),
        ],
        resolved_models={
            ("faux", "alpha"): Model(
                id="alpha",
                provider="faux",
                endpoint="coding",
                name="Faux Alpha",
                capabilities=Capabilities(
                    input=("text",),
                    context_window=128_000,
                    max_tokens=8_192,
                    reasoning=False,
                ),
                pricing=Pricing(input=1, output=2, cache_read=0.1, cache_write=0.2),
            ),
            ("openai", "gpt-5"): Model(
                id="gpt-5",
                provider="openai",
                endpoint="coding",
                name="GPT-5",
                capabilities=Capabilities(
                    input=("text", "image"),
                    context_window=400_000,
                    max_tokens=16_384,
                    reasoning=True,
                ),
                pricing=Pricing(input=5, output=15, cache_read=0.5, cache_write=0.8),
                adapter=OpenAICompletionsConfig(reasoning_effort=True),
            ),
        },
        endpoints={
            ("faux", "coding"): Endpoint(
                id="coding",
                api="openai-completions",
                provider="faux",
                base_url="https://api.faux.test/v1",
            ),
            ("openai", "coding"): Endpoint(
                id="coding",
                api="openai-responses",
                provider="openai",
                base_url="https://api.openai.test/v1",
            ),
        },
    )
    asyncio.run(session.set_model(ModelSelection(provider="faux", model_id="alpha")))
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "cycle-model", "type": "cycle_model"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_model_calls == [
        ModelSelection(provider="faux", model_id="alpha"),
        ModelSelection(provider="openai", model_id="gpt-5"),
    ]

    assert _parse_jsonl(stdout) == [
        {
            "id": "cycle-model",
            "type": "response",
            "command": "cycle_model",
            "success": True,
            "data": {
                "model": {
                    "provider": "openai",
                    "id": "gpt-5",
                    "name": "GPT-5",
                    "api": "openai-responses",
                    "baseUrl": "https://api.openai.test/v1",
                    "input": ["text", "image"],
                    "contextWindow": 400_000,
                    "maxTokens": 16_384,
                    "reasoning": True,
                    "cost": {
                        "input": 5,
                        "output": 15,
                        "cacheRead": 0.5,
                        "cacheWrite": 0.8,
                    },
                },
                "thinkingLevel": "off",
                "isScoped": False,
            },
        }
    ]


def test_rpc_mode_cycle_model_returns_explicit_null_data_when_no_models_exist() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "cycle-model", "type": "cycle_model"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "cycle-model",
            "type": "response",
            "command": "cycle_model",
            "success": True,
            "data": None,
        }
    ]


def test_rpc_mode_cycle_model_reports_invalid_model_registry_response_type() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class InvalidTypeSession(FakeSession):
        def get_available_models(self):
            return "not-a-list"

    session = InvalidTypeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(json.dumps({"id": "cycle-model", "type": "cycle_model"}) + "\n")
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout) == [
        {
            "id": "cycle-model",
            "type": "response",
            "command": "cycle_model",
            "success": False,
            "error": "Model registry returned an invalid response.",
        }
    ]


def test_rpc_mode_supports_bash_command() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "bash", "type": "bash", "command": "printf hi"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.bash_calls == [
        {
            "command": "printf hi",
            "cwd": None,
            "env": None,
            "timeout_seconds": None,
            "stdin": None,
        }
    ]
    assert _parse_jsonl(stdout) == [
        {
            "id": "bash",
            "type": "response",
            "command": "bash",
            "success": True,
            "data": {
                "output": "ok\n",
                "exitCode": 0,
                "cancelled": False,
                "truncated": False,
                "fullOutputPath": None,
            },
        }
    ]


def test_rpc_mode_allows_aborting_active_bash_command() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    session._bash_started = asyncio.Event()
    session._bash_release = asyncio.Event()
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "bash", "type": "bash", "command": "sleep 1"}),
                json.dumps({"id": "abort-bash", "type": "abort_bash"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await asyncio.wait_for(mode.run(), timeout=0.5)
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.abort_bash_calls == 1
    lines = _parse_jsonl(stdout)
    assert lines[0] == {
        "id": "abort-bash",
        "type": "response",
        "command": "abort_bash",
        "success": True,
    }
    assert lines[1] == {
        "id": "bash",
        "type": "response",
        "command": "bash",
        "success": True,
        "data": {
            "output": "partial\n",
            "exitCode": None,
            "cancelled": True,
            "truncated": False,
            "fullOutputPath": None,
        },
    }


def test_rpc_mode_supports_clone_and_get_fork_messages() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    current = FakeSession(session_id="session-a", cwd="/tmp/project-a")
    current.user_messages_for_forking = [
        {"entry_id": "u1", "text": "first"},
        {"entry_id": "u2", "text": "second"},
    ]
    next_session = FakeSession(session_id="session-b", cwd="/tmp/project-b")
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"id": "fork-messages", "type": "get_fork_messages"}),
                json.dumps({"id": "clone", "type": "clone"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert runtime.fork_session_calls == ["leaf-1"]
    lines = _parse_jsonl(stdout)
    assert lines[0] == {
        "id": "fork-messages",
        "type": "response",
        "command": "get_fork_messages",
        "success": True,
        "data": {
            "messages": [
                {"entryId": "u1", "text": "first"},
                {"entryId": "u2", "text": "second"},
            ]
        },
    }
    assert lines[1] == {
        "id": "clone",
        "type": "response",
        "command": "clone",
        "success": True,
        "data": {"cancelled": False},
    }


def test_rpc_mode_get_fork_messages_uses_standard_session_method() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class StandardForkSession(FakeSession):
        def get_user_messages_for_forking(self):
            return [{"entry_id": "u1", "text": "first"}]

    session = StandardForkSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "fork-messages", "type": "get_fork_messages"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    assert _parse_jsonl(stdout)[0]["data"] == {
        "messages": [{"entryId": "u1", "text": "first"}]
    }


def test_rpc_mode_reports_invalid_json_and_unsupported_commands() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdin = StringIO(
        "{invalid json}\n" + json.dumps({"id": "oops", "type": "unknown"}) + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    invalid, unsupported = _parse_jsonl(stdout)
    assert invalid["type"] == "response"
    assert invalid["command"] == "parse"
    assert invalid["success"] is False
    assert "Failed to parse command" in invalid["error"]

    assert unsupported["type"] == "response"
    assert unsupported["command"] == "unknown"
    assert unsupported["success"] is False
    assert "unsupported command" in unsupported["error"]
    assert unsupported["errorCode"] == "unsupported_command"
    assert unsupported["errorInfo"]["message"] == unsupported["error"]
    assert unsupported["errorInfo"]["command"] == "unknown"


def test_rpc_mode_rejects_non_finite_input_numbers() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        "\n".join(
            [
                '{"type":"get_state","value":NaN}',
                '{"type":"get_state","value":Infinity}',
                '{"type":"get_state","value":-Infinity}',
                '{"id":"bash","type":"bash","command":"printf hi","timeoutSeconds":1e400}',
                '{"id":"prompt","type":"prompt","message":"\\ud800"}',
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    responses = _parse_jsonl(stdout)
    assert session.bash_calls == []
    assert session.prompt_calls == []
    assert [response["command"] for response in responses[:3]] == [
        "parse",
        "parse",
        "parse",
    ]
    assert [response["error"] for response in responses[:3]] == [
        "Failed to parse command: invalid JSON numeric constant: NaN",
        "Failed to parse command: invalid JSON numeric constant: Infinity",
        "Failed to parse command: invalid JSON numeric constant: -Infinity",
    ]
    assert responses[3] == {
        "id": "bash",
        "type": "response",
        "command": "invalid",
        "success": False,
        "error": (
            "RPC command contains a value outside strict JSON: "
            "rpc_command.timeoutSeconds must be JSON-safe: non-finite float"
        ),
    }
    assert responses[4] == {
        "id": "prompt",
        "type": "response",
        "command": "invalid",
        "success": False,
        "error": (
            "RPC command contains a value outside strict JSON: "
            "rpc_command.message must be JSON-safe: string is not valid UTF-8"
        ),
    }


def test_rpc_mode_jsonl_framing_preserves_unicode_line_separators() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    name = "alpha\u2028beta\u2029gamma"
    stdin = StringIO(
        json.dumps(
            {"id": "rename", "type": "set_session_name", "name": name},
            ensure_ascii=False,
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_session_name_calls == [name]
    assert _parse_jsonl(stdout) == [
        {
            "id": "rename",
            "type": "response",
            "command": "set_session_name",
            "success": True,
        }
    ]


def test_rpc_mode_jsonl_framing_accepts_crlf_and_final_line_without_lf() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    session = FakeSession(session_id="session-a", cwd="/tmp/project")
    runtime = FakeRuntime(session)
    stdin = StringIO(
        json.dumps({"id": "first", "type": "set_session_name", "name": "one"})
        + "\r\n"
        + json.dumps({"id": "second", "type": "set_session_name", "name": "two"})
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    assert session.set_session_name_calls == ["one", "two"]
    assert _parse_jsonl(stdout) == [
        {
            "id": "first",
            "type": "response",
            "command": "set_session_name",
            "success": True,
        },
        {
            "id": "second",
            "type": "response",
            "command": "set_session_name",
            "success": True,
        },
    ]


def test_rpc_mode_ignores_unmatched_extension_ui_responses() -> None:
    from loushang.harness.host.rpc import run_rpc_host as run_rpc_mode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdin = StringIO(
        "\n".join(
            [
                json.dumps(
                    {"id": "ui-1", "type": "extension_ui_response", "value": "ignored"}
                ),
                json.dumps({"id": "state", "type": "get_state"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    async def scenario() -> None:
        exit_code = await run_rpc_mode(runtime=runtime, stdin=stdin, stdout=stdout)
        assert exit_code == 0

    asyncio.run(scenario())

    lines = _parse_jsonl(stdout)
    assert len(lines) == 1
    assert lines[0]["id"] == "state"
    assert lines[0]["command"] == "get_state"


def test_rpc_mode_extension_ui_context_emits_side_effect_requests() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()
    mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)

    mode.extension_ui_context.notify("Build finished", "info")
    mode.extension_ui_context.set_status("deploy", "running")
    mode.extension_ui_context.set_title("Deploying")
    mode.extension_ui_context.set_editor_text("next prompt")
    mode.extension_ui_context.set_widget(
        "summary", ["line 1", "line 2"], placement="belowEditor"
    )

    lines = _parse_jsonl(stdout)
    assert [line["method"] for line in lines] == [
        "notify",
        "setStatus",
        "setTitle",
        "set_editor_text",
        "setWidget",
    ]
    assert lines[0]["message"] == "Build finished"
    assert lines[0]["notifyType"] == "info"
    assert lines[1]["statusKey"] == "deploy"
    assert lines[1]["statusText"] == "running"
    assert lines[2]["title"] == "Deploying"
    assert lines[3]["text"] == "next prompt"
    assert lines[4]["widgetKey"] == "summary"
    assert lines[4]["widgetLines"] == ["line 1", "line 2"]
    assert lines[4]["widgetPlacement"] == "belowEditor"


def test_rpc_mode_exposes_extension_ui_state_snapshot() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()
    mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)

    mode.extension_ui_context.notify("Build finished", "info")
    mode.extension_ui_context.set_status("deploy", "running")
    mode.extension_ui_context.set_title("Deploying")
    mode.extension_ui_context.set_editor_text("next prompt")
    mode.extension_ui_context.set_widget("summary", ["line 1"], placement="belowEditor")
    mode._handle_get_extension_ui_state_command("ui-state", {})

    response = _parse_jsonl(stdout)[-1]
    assert response == {
        "id": "ui-state",
        "type": "response",
        "command": "get_extension_ui_state",
        "success": True,
        "data": {
            "notifications": [{"message": "Build finished", "notifyType": "info"}],
            "statuses": {"deploy": "running"},
            "widgets": {"summary": {"lines": ["line 1"], "placement": "belowEditor"}},
            "title": "Deploying",
            "editorText": "next prompt",
        },
    }


def test_rpc_mode_extension_ui_context_resolves_dialog_responses() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
        task = asyncio.create_task(
            mode.extension_ui_context.select("Choose target", ["dev", "prod"])
        )
        await asyncio.sleep(0)
        request = _parse_jsonl(stdout)[0]
        assert request["type"] == "extension_ui_request"
        assert request["method"] == "select"
        assert request["title"] == "Choose target"
        assert request["options"] == ["dev", "prod"]
        await mode._handle_line(
            json.dumps(
                {"type": "extension_ui_response", "id": request["id"], "value": "prod"}
            )
        )
        assert await asyncio.wait_for(task, timeout=0.5) == "prod"

    asyncio.run(scenario())


def test_rpc_mode_extension_ui_context_resolves_confirm_input_and_editor_responses() -> (
    None
):
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
        confirm_task = asyncio.create_task(
            mode.extension_ui_context.confirm("Deploy?", "Ship to prod?")
        )
        input_task = asyncio.create_task(
            mode.extension_ui_context.input("Branch", "main")
        )
        editor_task = asyncio.create_task(
            mode.extension_ui_context.editor("Edit prompt", "draft")
        )
        await asyncio.sleep(0)
        requests = _parse_jsonl(stdout)
        assert [request["method"] for request in requests] == [
            "confirm",
            "input",
            "editor",
        ]
        assert requests[0]["message"] == "Ship to prod?"
        assert requests[1]["placeholder"] == "main"
        assert requests[2]["prefill"] == "draft"
        await mode._handle_line(
            json.dumps(
                {
                    "type": "extension_ui_response",
                    "id": requests[0]["id"],
                    "confirmed": True,
                }
            )
        )
        await mode._handle_line(
            json.dumps(
                {
                    "type": "extension_ui_response",
                    "id": requests[1]["id"],
                    "value": "feature",
                }
            )
        )
        await mode._handle_line(
            json.dumps(
                {
                    "type": "extension_ui_response",
                    "id": requests[2]["id"],
                    "value": "edited",
                }
            )
        )
        assert await asyncio.wait_for(confirm_task, timeout=0.5) is True
        assert await asyncio.wait_for(input_task, timeout=0.5) == "feature"
        assert await asyncio.wait_for(editor_task, timeout=0.5) == "edited"

    asyncio.run(scenario())


def test_rpc_mode_binds_extension_context_ui_methods_to_rpc_requests(tmp_path) -> None:
    from loushang.agent import Agent
    from loushang.coding.session import AgentSession
    from loushang.coding.session_manager import SessionManager
    from loushang.harness.extensions.agent import ExtensionRunner, LoadedExtension
    from loushang.harness.host.rpc import RpcHost as RpcMode

    extension_runner = ExtensionRunner(
        [
            LoadedExtension(
                name="rpc-ui",
                source_path=Path("/tmp/rpc_ui.py"),
            )
        ]
    )
    session = AgentSession(
        agent=Agent(
            initial_state={
                "system_prompt": "",
                "model": Model(
                    id="tiny",
                    provider="faux",
                    endpoint="test",
                    capabilities=Capabilities(
                        input=("text",), context_window=10_000, max_tokens=1024
                    ),
                ),
                "thinking_level": "off",
            }
        ),
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
        extension_runner=extension_runner,
    )
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
    context = extension_runner.create_command_context(fallback_cwd="/tmp/project")
    context.notify("Starting", "info")
    context.set_title("Working")
    context.set_status("phase", "prompt")

    requests = _parse_jsonl(stdout)
    assert [request["method"] for request in requests] == [
        "notify",
        "setTitle",
        "setStatus",
    ]


def test_rpc_mode_extension_context_excludes_pi_style_camel_case_ui_methods(
    tmp_path,
) -> None:
    from loushang.agent import Agent
    from loushang.coding.session import AgentSession
    from loushang.coding.session_manager import SessionManager
    from loushang.harness.extensions.agent import ExtensionRunner, LoadedExtension
    from loushang.harness.host.rpc import RpcHost as RpcMode

    extension_runner = ExtensionRunner(
        [LoadedExtension(name="rpc-ui", source_path=Path("/tmp/rpc_ui.py"))]
    )
    session = AgentSession(
        agent=Agent(
            initial_state={
                "system_prompt": "",
                "model": Model(
                    id="tiny",
                    provider="faux",
                    endpoint="test",
                    capabilities=Capabilities(
                        input=("text",), context_window=10_000, max_tokens=1024
                    ),
                ),
                "thinking_level": "off",
            }
        ),
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
        extension_runner=extension_runner,
    )
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
    context = extension_runner.create_command_context(fallback_cwd="/tmp/project")
    for method_name in ("setStatus", "setTitle", "setEditorText", "setWidget"):
        assert not hasattr(context, method_name)
    assert _parse_jsonl(stdout) == []


def test_rpc_mode_extension_context_ui_namespace_is_snake_case_only(tmp_path) -> None:
    from loushang.agent import Agent
    from loushang.coding.session import AgentSession
    from loushang.coding.session_manager import SessionManager
    from loushang.harness.extensions.agent import ExtensionRunner, LoadedExtension
    from loushang.harness.host.rpc import RpcHost as RpcMode

    extension_runner = ExtensionRunner(
        [LoadedExtension(name="rpc-ui", source_path=Path("/tmp/rpc_ui.py"))]
    )
    session = AgentSession(
        agent=Agent(
            initial_state={
                "system_prompt": "",
                "model": Model(
                    id="tiny",
                    provider="faux",
                    endpoint="test",
                    capabilities=Capabilities(
                        input=("text",), context_window=10_000, max_tokens=1024
                    ),
                ),
                "thinking_level": "off",
            }
        ),
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
        extension_runner=extension_runner,
    )
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
    context = extension_runner.create_command_context(fallback_cwd="/tmp/project")
    assert context.has_ui is True
    for method_name in ("setStatus", "setTitle", "setEditorText"):
        assert not hasattr(context.ui, method_name)
    context.ui.set_status("deploy", "running")
    context.ui.set_title("Deploying")
    context.ui.set_editor_text("next prompt")

    requests = _parse_jsonl(stdout)
    assert [request["method"] for request in requests] == [
        "setStatus",
        "setTitle",
        "set_editor_text",
    ]


def test_rpc_mode_extension_context_excludes_pi_style_headless_ui_methods(
    tmp_path,
) -> None:
    from loushang.agent import Agent
    from loushang.coding.session import AgentSession
    from loushang.coding.session_manager import SessionManager
    from loushang.harness.extensions.agent import ExtensionRunner, LoadedExtension
    from loushang.harness.host.rpc import RpcHost as RpcMode

    extension_runner = ExtensionRunner(
        [LoadedExtension(name="rpc-ui", source_path=Path("/tmp/rpc_ui.py"))]
    )
    session = AgentSession(
        agent=Agent(
            initial_state={
                "system_prompt": "",
                "model": Model(
                    id="tiny",
                    provider="faux",
                    endpoint="test",
                    capabilities=Capabilities(
                        input=("text",), context_window=10_000, max_tokens=1024
                    ),
                ),
                "thinking_level": "off",
            }
        ),
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
        extension_runner=extension_runner,
    )
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
    ui = extension_runner.create_command_context(fallback_cwd="/tmp/project").ui
    for method_name in (
        "onTerminalInput",
        "setWorkingMessage",
        "setWorkingVisible",
        "setWorkingIndicator",
        "setHiddenThinkingLabel",
        "setFooter",
        "setHeader",
        "addAutocompleteProvider",
        "setEditorComponent",
        "getAllThemes",
        "getTheme",
        "setTheme",
        "getToolsExpanded",
        "setToolsExpanded",
    ):
        assert not hasattr(ui, method_name)
    assert _parse_jsonl(stdout) == []


def test_rpc_mode_extension_ui_dialog_timeout_returns_default_values() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
        assert (
            await mode.extension_ui_context.select("Target", ["dev"], timeout=0.01)
            is None
        )
        assert (
            await mode.extension_ui_context.confirm("Confirm", "Proceed?", timeout=0.01)
            is False
        )
        assert await mode.extension_ui_context.input("Input", timeout=0.01) is None
        assert await mode.extension_ui_context.editor("Edit", timeout=0.01) is None

    asyncio.run(scenario())

    requests = _parse_jsonl(stdout)
    assert [request["method"] for request in requests] == [
        "select",
        "confirm",
        "input",
        "editor",
    ]
    assert all(request["timeout"] == 0.01 for request in requests)


def test_rpc_mode_extension_ui_late_response_after_timeout_is_ignored() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
        assert (
            await mode.extension_ui_context.select("Target", ["dev"], timeout=0.01)
            is None
        )
        expired_request = _parse_jsonl(stdout)[0]
        await mode._handle_line(
            json.dumps(
                {
                    "type": "extension_ui_response",
                    "id": expired_request["id"],
                    "value": "dev",
                }
            )
        )
        task = asyncio.create_task(mode.extension_ui_context.select("Target", ["prod"]))
        await asyncio.sleep(0)
        active_request = _parse_jsonl(stdout)[1]
        await mode._handle_line(
            json.dumps(
                {
                    "type": "extension_ui_response",
                    "id": active_request["id"],
                    "value": "prod",
                }
            )
        )
        assert await asyncio.wait_for(task, timeout=0.5) == "prod"

    asyncio.run(scenario())


def test_rpc_mode_extension_ui_dialog_cancelled_responses_return_defaults() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
        select_task = asyncio.create_task(
            mode.extension_ui_context.select("Target", ["dev"])
        )
        confirm_task = asyncio.create_task(
            mode.extension_ui_context.confirm("Confirm", "Proceed?")
        )
        await asyncio.sleep(0)
        requests = _parse_jsonl(stdout)
        for request in requests:
            await mode._handle_line(
                json.dumps(
                    {
                        "type": "extension_ui_response",
                        "id": request["id"],
                        "cancelled": True,
                    }
                )
            )
        assert await asyncio.wait_for(select_task, timeout=0.5) is None
        assert await asyncio.wait_for(confirm_task, timeout=0.5) is False

    asyncio.run(scenario())


def test_rpc_mode_write_json_line_rejects_circular_payloads() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()
    mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)

    payload: dict[str, object] = {
        "type": "response",
        "command": "probe",
        "success": True,
    }
    payload["data"] = payload

    mode._write_json_line(payload)
    assert _parse_jsonl(stdout) == [
        {
            "type": "response",
            "command": "probe",
            "success": False,
            "error": "Failed to serialize RPC output.",
        }
    ]


def test_rpc_mode_write_json_line_preserves_command_on_fallback() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class BadSlots:
        __slots__ = ()

        def __repr__(self) -> str:  # pragma: no cover
            raise RuntimeError("unprintable")

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()
    mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)

    mode._write_json_line(
        {"type": "response", "id": "id-1", "command": "probe", "data": BadSlots()}
    )
    assert _parse_jsonl(stdout) == [
        {
            "type": "response",
            "command": "probe",
            "success": False,
            "error": "Failed to serialize RPC output.",
            "id": "id-1",
        },
    ]


def test_rpc_mode_write_json_line_drops_invalid_fallback_fields() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class Unsupported:
        pass

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = StringIO()
    mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)

    mode._write_json_line(
        {
            "type": "response",
            "id": "\ud800",
            "command": "\ud800",
            "data": Unsupported(),
        }
    )

    rendered = stdout.getvalue()
    rendered.encode("utf-8")
    assert _parse_jsonl(stdout) == [
        {
            "type": "response",
            "command": "response",
            "success": False,
            "error": "Failed to serialize RPC output.",
        }
    ]


def test_rpc_mode_write_json_line_flushes_output() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode

    class FlushingStringIO(StringIO):
        def __init__(self) -> None:
            super().__init__()
            self.flush_calls = 0

        def flush(self) -> None:
            self.flush_calls += 1
            super().flush()

    runtime = FakeRuntime(FakeSession(session_id="session-a", cwd="/tmp/project"))
    stdout = FlushingStringIO()
    mode = RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)

    mode._write_json_line({"type": "response", "command": "probe", "success": True})

    assert stdout.flush_calls == 1
    assert _parse_jsonl(stdout) == [
        {"type": "response", "command": "probe", "success": True}
    ]


def test_rpc_mode_rebinds_extension_ui_context_after_session_switch(tmp_path) -> None:
    from loushang.agent import Agent
    from loushang.coding.session import AgentSession
    from loushang.coding.session_manager import SessionManager
    from loushang.harness.extensions.agent import ExtensionRunner, LoadedExtension
    from loushang.harness.host.rpc import RpcHost as RpcMode

    def _session(session_id: str, extension_runner: ExtensionRunner) -> AgentSession:
        return AgentSession(
            agent=Agent(
                initial_state={
                    "system_prompt": "",
                    "model": Model(
                        id="tiny",
                        provider="faux",
                        endpoint="test",
                        capabilities=Capabilities(
                            input=("text",), context_window=10_000, max_tokens=1024
                        ),
                    ),
                    "thinking_level": "off",
                }
            ),
            session_manager=asyncio.run(
                SessionManager.new(
                    session_dir=tmp_path / session_id, cwd="/tmp/project", persist=False
                )
            ),
            extension_runner=extension_runner,
        )

    first_runner = ExtensionRunner(
        [LoadedExtension(name="first", source_path=Path("/tmp/first.py"))]
    )
    second_runner = ExtensionRunner(
        [LoadedExtension(name="second", source_path=Path("/tmp/second.py"))]
    )
    current = _session("a", first_runner)
    next_session = _session("b", second_runner)
    runtime = FakeRuntime(current)
    runtime.queue_next_session(next_session)
    stdout = StringIO()
    stdin = StringIO(
        json.dumps({"id": "switch", "type": "switch_session", "sessionId": "session-b"})
        + "\n"
    )

    async def scenario() -> None:
        mode = RpcMode(runtime=runtime, stdin=stdin, stdout=stdout)
        exit_code = await mode.run()
        assert exit_code == 0

    asyncio.run(scenario())

    second_runner.create_command_context(fallback_cwd="/tmp/project").notify(
        "Rebound", "info"
    )
    requests = [
        line for line in _parse_jsonl(stdout) if line["type"] == "extension_ui_request"
    ]
    assert len(requests) == 1
    assert requests[0]["message"] == "Rebound"


def test_rpc_mode_emits_extension_error_for_hook_failures(tmp_path) -> None:
    from loushang.agent import Agent
    from loushang.coding.session import AgentSession
    from loushang.coding.session_manager import SessionManager
    from loushang.harness.extensions.agent import ExtensionRunner, LoadedExtension
    from loushang.harness.host.rpc import RpcHost as RpcMode

    def _broken_hook(session, ctx):
        del session, ctx
        raise RuntimeError("hook exploded")

    extension_runner = ExtensionRunner(
        [
            LoadedExtension(
                name="broken",
                source_path=Path("/tmp/broken.py"),
                hooks={"session_start": [_broken_hook]},
            )
        ]
    )
    session = AgentSession(
        agent=Agent(
            initial_state={
                "system_prompt": "",
                "model": Model(
                    id="tiny",
                    provider="faux",
                    endpoint="test",
                    capabilities=Capabilities(
                        input=("text",), context_window=10_000, max_tokens=1024
                    ),
                ),
                "thinking_level": "off",
            }
        ),
        session_manager=asyncio.run(
            SessionManager.new(session_dir=tmp_path, cwd="/tmp/project", persist=False)
        ),
        extension_runner=extension_runner,
    )
    runtime = FakeRuntime(session)
    stdout = StringIO()

    RpcMode(runtime=runtime, stdin=StringIO(""), stdout=stdout)
    asyncio.run(extension_runner.emit_session_start(session))

    lines = _parse_jsonl(stdout)
    assert lines == [
        {
            "type": "extension_error",
            "extensionPath": "/tmp/broken.py",
            "event": "session_start",
            "error": "hook exploded",
        }
    ]


def test_rpc_mode_is_exported_from_shared_host_package() -> None:
    from loushang.harness.host.rpc import RpcHost as RpcMode
    from loushang.harness.host.rpc import run_rpc_host

    assert RpcMode is not None
    assert run_rpc_host is not None
