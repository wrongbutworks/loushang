from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loushang.agent import AbortController, Agent
from loushang.ai.types import UserMessage
from loushang.coding.compaction import (
    BranchSummaryDetails,
    collect_entries_for_branch_summary,
    generate_branch_summary,
)
from loushang.coding.event import AgentSessionEvent
from loushang.coding.extensions import ExtensionRunner, SessionBeforeTreeEvent
from loushang.coding.message import CustomMessageEntry, SessionMessageEntry
from loushang.coding.session.types import TreeNavigationResult
from loushang.coding.store import SessionManager
from loushang.protocol import JSONValue, require_json_value

EventDispatcher = Callable[[AgentSessionEvent], Awaitable[None]]
RuntimeExceptionRecorder = Callable[..., None]
ExtensionDiagnosticsSync = Callable[..., None]
BranchSummaryGenerator = Callable[..., Awaitable[Any]]


def _noop_record_runtime_exception(*, code: str, exc: Exception | str) -> None:
    del code, exc


def _noop_sync_extension_diagnostics(*, phase: str) -> None:
    del phase


@dataclass
class TreeController:
    agent: Agent
    session_manager: SessionManager
    dispatch_event: EventDispatcher
    extension_runner: ExtensionRunner | None = None
    record_runtime_exception: RuntimeExceptionRecorder = _noop_record_runtime_exception
    sync_extension_diagnostics: ExtensionDiagnosticsSync = _noop_sync_extension_diagnostics

    _branch_summary_abort_controller: AbortController | None = None

    @property
    def is_branch_summarizing(self) -> bool:
        return self._branch_summary_abort_controller is not None

    async def navigate_tree(
        self,
        target_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
        label: str | None = None,
        generate_branch_summary_fn: BranchSummaryGenerator | None = None,
    ) -> TreeNavigationResult:
        old_leaf_id = self.session_manager.get_leaf_id()
        if target_id == old_leaf_id:
            return TreeNavigationResult(cancelled=False)

        target_entry = self.session_manager.get_entry(target_id)
        if target_entry is None:
            raise ValueError(f"Entry {target_id} not found")

        editor_text: str | None = None
        if isinstance(target_entry, SessionMessageEntry) and isinstance(target_entry.message, UserMessage):
            new_leaf_id = target_entry.parent_id
            editor_text = _extract_user_message_text(target_entry.message)
        elif isinstance(target_entry, CustomMessageEntry):
            new_leaf_id = target_entry.parent_id
            editor_text = _extract_custom_message_text(target_entry)
        else:
            new_leaf_id = target_id

        summary_result = None
        if self.extension_runner is not None:
            decision = await self.extension_runner.before_session_tree(
                SessionBeforeTreeEvent(
                    target_id=target_id,
                    old_leaf_id=old_leaf_id,
                    new_leaf_id=new_leaf_id,
                    cwd=str(self.session_manager.get_cwd()),
                    summarize=summarize,
                    custom_instructions=custom_instructions,
                    replace_instructions=replace_instructions,
                    label=label,
                )
            )
            if decision is not None and decision.cancel:
                self.sync_extension_diagnostics(phase="runtime")
                return TreeNavigationResult(cancelled=True)
            if decision is not None and decision.summary is not None:
                summary_result = decision.summary
            else:
                summary_result = None
            if decision is not None and decision.custom_instructions is not None:
                custom_instructions = decision.custom_instructions
            if decision is not None and decision.replace_instructions is not None:
                replace_instructions = decision.replace_instructions
            if decision is not None and decision.label is not None:
                label = decision.label

        if not summarize:
            self._apply_navigation_leaf(new_leaf_id)
            self._rebuild_agent_context()
            if self.extension_runner is not None:
                await self.extension_runner.emit_event(
                    {
                        "type": "session_tree",
                        "new_leaf_id": new_leaf_id,
                        "old_leaf_id": old_leaf_id,
                        "summary_entry": None,
                        "from_extension": False,
                    },
                    cwd=self.session_manager.get_cwd(),
                )
            return TreeNavigationResult(
                cancelled=False,
                editor_text=editor_text,
            )

        await self.dispatch_event(
            {
                "type": "branch_summary_start",
                "target_id": target_id,
                "old_leaf_id": old_leaf_id,
                "summarize": True,
            }
        )

        self._branch_summary_abort_controller = AbortController()
        summary_from_hook = False
        summary_entry_id: str | None = None
        if summary_result is not None:
            summary_entry_id = self.session_manager.branch_with_summary(
                new_leaf_id,
                summary_result.summary,
                details=_project_branch_summary_details(summary_result.details),
                from_hook=True,
            )
            summary_from_hook = True
            if label:
                self.session_manager.append_label(summary_entry_id, label)

        try:
            entries_to_summarize = collect_entries_for_branch_summary(
                self.session_manager,
                old_leaf_id,
                target_id,
            ).entries
            if entries_to_summarize and summary_result is None:
                generate = generate_branch_summary_fn or generate_branch_summary
                summary_result = await generate(
                    entries_to_summarize,
                    model=self.agent.model,
                    api_key="",
                    signal=self._branch_summary_abort_controller.signal,
                    custom_instructions=custom_instructions,
                    replace_instructions=replace_instructions,
                )
                if summary_result.aborted:
                    await self.dispatch_event(
                        {
                            "type": "branch_summary_end",
                            "target_id": target_id,
                            "old_leaf_id": old_leaf_id,
                            "new_leaf_id": old_leaf_id,
                            "summary_entry_id": None,
                            "cancelled": True,
                            "aborted": True,
                        }
                    )
                    return TreeNavigationResult(cancelled=True, aborted=True)
                if summary_result.error:
                    self.record_runtime_exception(code="branch_summary_failed", exc=summary_result.error)
                    await self.dispatch_event(
                        {
                            "type": "branch_summary_end",
                            "target_id": target_id,
                            "old_leaf_id": old_leaf_id,
                            "new_leaf_id": old_leaf_id,
                            "summary_entry_id": None,
                            "cancelled": False,
                            "aborted": False,
                            "error_message": summary_result.error,
                        }
                    )
                    raise RuntimeError(summary_result.error)
                if summary_result.summary:
                    summary_entry_id = self.session_manager.branch_with_summary(
                        new_leaf_id,
                        summary_result.summary,
                        details=_project_branch_summary_details(summary_result.details),
                        from_hook=summary_from_hook,
                    )
                    if label:
                        self.session_manager.append_label(summary_entry_id, label)

            if summary_entry_id is None:
                self._apply_navigation_leaf(new_leaf_id)
                if label:
                    self.session_manager.append_label(target_id, label)

            self._rebuild_agent_context()
            await self.dispatch_event(
                {
                    "type": "branch_summary_end",
                    "target_id": target_id,
                    "old_leaf_id": old_leaf_id,
                    "new_leaf_id": self.session_manager.get_leaf_id(),
                    "summary_entry_id": summary_entry_id,
                    "cancelled": False,
                    "aborted": False,
                }
            )
            return TreeNavigationResult(
                cancelled=False,
                editor_text=editor_text,
                summary_entry_id=summary_entry_id,
            )
        except Exception as exc:
            self.record_runtime_exception(code="branch_summary_failed", exc=exc)
            await self.dispatch_event(
                {
                    "type": "branch_summary_end",
                    "target_id": target_id,
                    "old_leaf_id": old_leaf_id,
                    "new_leaf_id": old_leaf_id,
                    "summary_entry_id": None,
                    "cancelled": False,
                    "aborted": False,
                    "error_message": str(exc),
                }
            )
            raise
        finally:
            self._branch_summary_abort_controller = None

    def abort_branch_summary(self) -> None:
        if self._branch_summary_abort_controller is not None:
            self._branch_summary_abort_controller.abort()

    def _apply_navigation_leaf(self, new_leaf_id: str | None) -> None:
        if new_leaf_id is None:
            self.session_manager.reset_leaf()
        else:
            self.session_manager.branch(new_leaf_id)

    def _rebuild_agent_context(self) -> None:
        session_context = self.session_manager.build_session_context()
        self.agent.state.set_messages(session_context.messages)


def _extract_user_message_text(message: UserMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")


def _extract_custom_message_text(entry: CustomMessageEntry) -> str:
    if isinstance(entry.content, str):
        return entry.content
    return "".join(block.text for block in entry.content if getattr(block, "type", None) == "text")


def _project_branch_summary_details(details: object | None) -> JSONValue:
    if isinstance(details, BranchSummaryDetails):
        return {
            "readFiles": list(details.read_files),
            "modifiedFiles": list(details.modified_files),
        }
    return require_json_value(details, name="branch_summary.details")
