from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any

from loushang.agent import Agent
from loushang.ai.types import AssistantMessage
from loushang.ai.utils import is_context_overflow
from loushang.coding.compaction import (
    CompactionPreparation,
    CompactionResult,
    prepare_compaction,
)
from loushang.coding.compaction import (
    compact as run_compaction,
)
from loushang.coding.control import CompactionSettings
from loushang.coding.event import AgentSessionEvent
from loushang.coding.extensions import ExtensionRunner, SessionBeforeCompactEvent
from loushang.coding.message import CompactionEntry
from loushang.coding.session.context_usage import (
    build_context_usage_snapshot,
    build_threshold_compaction_decision,
)
from loushang.coding.session.types import ContextUsageSnapshot
from loushang.coding.store import SessionManager

EventDispatcher = Callable[[AgentSessionEvent], Awaitable[None]]
ExtensionRunnerProvider = Callable[[], ExtensionRunner | None]
SettingsProvider = Callable[[], CompactionSettings]
RuntimeExceptionRecorder = Callable[..., None]
ExtensionDiagnosticsSync = Callable[..., None]
CompactionFunction = Callable[..., Awaitable[CompactionResult]]
PrepareCompactionFunction = Callable[[list[Any], int], CompactionPreparation]
ContextOverflowPredicate = Callable[[AssistantMessage, int], bool]
CompactInternalRunner = Callable[..., Awaitable[CompactionResult | None]]
ContinueRun = Callable[[], Awaitable[None]]


def _noop_record_runtime_exception(*, code: str, exc: Exception | str) -> None:
    del code, exc


def _noop_sync_extension_diagnostics(*, phase: str) -> None:
    del phase


@dataclass
class CompactionController:
    agent: Agent
    session_manager: SessionManager
    get_settings: SettingsProvider
    get_extension_runner: ExtensionRunnerProvider
    dispatch_event: EventDispatcher
    record_runtime_exception: RuntimeExceptionRecorder = _noop_record_runtime_exception
    sync_extension_diagnostics: ExtensionDiagnosticsSync = _noop_sync_extension_diagnostics

    _compaction_in_progress: bool = False
    _overflow_recovery_attempted: bool = False

    @property
    def is_compacting(self) -> bool:
        return self._compaction_in_progress

    def clear_overflow_recovery_attempted(self) -> None:
        self._overflow_recovery_attempted = False

    async def maybe_compact_after_turn(
        self,
        assistant_message: AssistantMessage,
        *,
        compact_internal_fn: CompactInternalRunner | None = None,
        continue_run_fn: ContinueRun | None = None,
        is_context_overflow_fn: ContextOverflowPredicate = is_context_overflow,
    ) -> CompactionResult | None:
        settings = self.get_settings()
        if not settings.enabled:
            return None

        context_window = self.agent.model.context_window or 0
        if context_window <= 0:
            return None
        latest_compaction = _latest_compaction_entry(self.session_manager.get_branch())
        if latest_compaction is not None and _message_is_before_or_at_entry(assistant_message, latest_compaction):
            return None
        run_compact = compact_internal_fn or self.compact
        if is_context_overflow_fn(assistant_message, context_window):
            if self._overflow_recovery_attempted:
                message = (
                    "Context overflow recovery failed after one compact-and-retry attempt. "
                    "Try reducing context or switching to a larger-context model."
                )
                await self.dispatch_event(
                    {
                        "type": "compaction_end",
                        "reason": "overflow",
                        "result": None,
                        "aborted": False,
                        "will_retry": True,
                        "error_message": message,
                        "usage_before": _snapshot_payload(self._build_usage_snapshot(settings)),
                        "usage_after": _snapshot_payload(self._build_usage_snapshot(settings)),
                    }
                )
                return None
            self._overflow_recovery_attempted = True
            result = await run_compact(reason="overflow", will_retry=True, raise_on_error=False)
            if result is not None and continue_run_fn is not None:
                asyncio.create_task(continue_run_fn())
            return result

        messages = list(self.session_manager.build_session_context().messages)
        if not any(message is assistant_message for message in messages):
            messages.append(assistant_message)
        decision = build_threshold_compaction_decision(
            messages,
            self.session_manager.get_branch(),
            self.agent.model,
            enabled=settings.enabled,
            reserve_tokens=settings.reserve_tokens,
            compact_percent=settings.compact_percent,
            keep_recent_tokens=settings.keep_recent_tokens,
        )
        if decision.usage.tokens is None:
            return None
        if decision.action == "threshold":
            result = await run_compact(reason="threshold", will_retry=False, raise_on_error=False)
            if result is not None and continue_run_fn is not None and self.agent.has_queued_messages():
                asyncio.create_task(continue_run_fn())
            return result
        return None

    async def compact(
        self,
        *,
        reason: str,
        will_retry: bool,
        raise_on_error: bool = True,
        custom_instructions: str | None = None,
        compact_fn: CompactionFunction = run_compaction,
        prepare_compaction_fn: PrepareCompactionFunction = prepare_compaction,
    ) -> CompactionResult | None:
        settings = self.get_settings()
        usage_before = self._build_usage_snapshot(settings)
        usage_before_payload = _snapshot_payload(usage_before)
        await self.dispatch_event({"type": "compaction_start", "reason": reason, "usage": usage_before_payload})
        self._compaction_in_progress = True
        try:
            preparation = prepare_compaction_fn(
                self.session_manager.get_branch(),
                settings.keep_recent_tokens,
            )
            if not preparation.messages_to_summarize and not preparation.turn_prefix_messages:
                raise RuntimeError("Nothing to compact (session too small)")

            result: CompactionResult | None = None
            from_hook = False
            extension_runner = self.get_extension_runner()
            if extension_runner is not None:
                decision = await extension_runner.before_session_compact(
                    SessionBeforeCompactEvent(
                        reason=reason,
                        cwd=str(self.session_manager.get_cwd()),
                        custom_instructions=custom_instructions,
                    )
                )
                if decision is not None and decision.cancel:
                    self.sync_extension_diagnostics(phase="runtime")
                    raise RuntimeError("Compaction cancelled")
                if getattr(decision, "compaction", None) is not None:
                    result = decision.compaction
                    from_hook = True

            if result is None:
                compact_kwargs = {
                    "preparation": preparation,
                    "model": self.agent.model,
                    "api_key": "",
                    "headers": None,
                    "signal": self.agent.signal,
                }
                if custom_instructions is not None:
                    compact_kwargs["custom_instructions"] = custom_instructions
                result = await compact_fn(**compact_kwargs)

            result = _with_preparation_details(result, preparation)
            self.session_manager.append_compaction(
                result.summary,
                result.first_kept_entry_id,
                result.tokens_before,
                details=result.details,
                from_hook=from_hook,
            )
            if extension_runner is not None:
                await extension_runner.emit_event(
                    {
                        "type": "session_compact",
                        "compaction": result,
                        "compaction_entry": self.session_manager.get_entry(self.session_manager.get_leaf_id() or ""),
                        "from_extension": from_hook,
                    },
                    cwd=self.session_manager.get_cwd(),
                )
            session_context = self.session_manager.build_session_context()
            self.agent.state.set_messages(session_context.messages)
            await self.dispatch_event(
                {
                    "type": "compaction_end",
                    "reason": reason,
                    "result": asdict(result),
                    "aborted": False,
                    "will_retry": will_retry,
                    "usage_before": usage_before_payload,
                    "usage_after": _snapshot_payload(self._build_usage_snapshot(settings)),
                }
            )
            return result
        except Exception as exc:
            message = str(exc)
            aborted = message == "Compaction cancelled" or getattr(exc, "name", None) == "AbortError"
            if not aborted:
                self.record_runtime_exception(code="compaction_failed", exc=exc)
            await self.dispatch_event(
                {
                    "type": "compaction_end",
                    "reason": reason,
                    "result": None,
                    "aborted": aborted,
                    "will_retry": will_retry,
                    "usage_before": usage_before_payload,
                    "usage_after": _snapshot_payload(self._build_usage_snapshot(settings)),
                    **({} if aborted else {"error_message": f"Compaction failed: {exc}"}),
                }
            )
            if raise_on_error:
                raise
            return None
        finally:
            self._compaction_in_progress = False

    def _build_usage_snapshot(self, settings: CompactionSettings) -> ContextUsageSnapshot:
        return build_context_usage_snapshot(
            list(self.session_manager.build_session_context().messages),
            self.session_manager.get_branch(),
            self.agent.model,
            reserve_tokens=settings.reserve_tokens,
            compact_percent=settings.compact_percent,
            keep_recent_tokens=settings.keep_recent_tokens,
        )


def _latest_compaction_entry(entries: list[object]) -> CompactionEntry | None:
    for entry in reversed(entries):
        if isinstance(entry, CompactionEntry):
            return entry
    return None


def _message_is_before_or_at_entry(message: AssistantMessage, entry: CompactionEntry) -> bool:
    entry_timestamp = _entry_timestamp_ms(entry.timestamp)
    if entry_timestamp is None:
        return False
    return message.timestamp <= entry_timestamp


def _entry_timestamp_ms(timestamp: str) -> float | None:
    try:
        normalized = timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp() * 1000
    except ValueError:
        return None


def _snapshot_payload(snapshot: ContextUsageSnapshot) -> dict[str, Any]:
    return asdict(snapshot)


def _with_preparation_details(
    result: CompactionResult,
    preparation: CompactionPreparation,
) -> CompactionResult:
    details = _merge_preparation_result_details(preparation.details, result.details)
    if details == result.details:
        return result
    return replace(result, details=details)


def _merge_preparation_result_details(preparation_details: object | None, result_details: object | None) -> object | None:
    if not isinstance(preparation_details, Mapping):
        return result_details if result_details is not None else preparation_details

    merged: dict[object, object] = dict(preparation_details)
    if isinstance(result_details, Mapping):
        merged.update(result_details)
        if "compactionPlan" in preparation_details:
            merged["compactionPlan"] = preparation_details["compactionPlan"]
        return merged

    if result_details is not None:
        merged["resultDetails"] = result_details
    return merged
