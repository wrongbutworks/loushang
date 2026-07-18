"""Coding adapter for Harness-owned Agent transcript compaction lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from loushang.agent import Agent
from loushang.ai.types import AssistantMessage
from loushang.ai.utils import is_context_overflow
from loushang.coding.compaction import (
    compact as run_compaction,
)
from loushang.coding.compaction import (
    prepare_compaction,
)
from loushang.coding.control import CompactionSettings
from loushang.coding.extensions import ExtensionRunner, SessionBeforeCompactEvent
from loushang.coding.store import SessionManager
from loushang.harness.agent_transcript import (
    AgentTranscriptCompactionRuntime,
    CompactionHookDecision,
    CompactionHookRequest,
    CompactionPreparation,
    CompactionResult,
    TranscriptCompactionPolicy,
)
from loushang.harness.events import CompactionReason, SessionRuntimeEventPayload

EventDispatcher = Callable[[SessionRuntimeEventPayload], Awaitable[None]]
ExtensionRunnerProvider = Callable[[], ExtensionRunner | None]
SettingsProvider = Callable[[], CompactionSettings]
RuntimeExceptionRecorder = Callable[..., None]
ExtensionDiagnosticsSync = Callable[..., None]
CompactionFunction = Callable[..., Awaitable[CompactionResult]]
PrepareCompactionFunction = Callable[[list[Any], int], CompactionPreparation]
CompactInternalRunner = Callable[..., Awaitable[CompactionResult | None]]
ContinueRun = Callable[[], Awaitable[None]]
ContextOverflowPredicate = Callable[[AssistantMessage, int], bool]


def _noop_record_runtime_exception(*, code: str, exc: Exception | str) -> None:
    del code, exc


def _noop_sync_extension_diagnostics(*, phase: str) -> None:
    del phase


@dataclass
class CompactionController:
    """Bind Coding compaction strategy and extension semantics to Harness."""

    agent: Agent
    session_manager: SessionManager
    get_settings: SettingsProvider
    get_extension_runner: ExtensionRunnerProvider
    dispatch_event: EventDispatcher
    record_runtime_exception: RuntimeExceptionRecorder = _noop_record_runtime_exception
    sync_extension_diagnostics: ExtensionDiagnosticsSync = (
        _noop_sync_extension_diagnostics
    )
    compact_fn: CompactionFunction = run_compaction
    prepare_compaction_fn: PrepareCompactionFunction = prepare_compaction
    _runtime: AgentTranscriptCompactionRuntime = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._runtime = AgentTranscriptCompactionRuntime(
            transcript=self.session_manager,
            get_policy=lambda: _compaction_policy(self.get_settings()),
            get_model=lambda: self.agent.model,
            get_context_messages=lambda: list(
                self.session_manager.build_session_context().messages
            ),
            refresh_context=self._refresh_agent_context,
            prepare_compaction=self._prepare_compaction,
            execute_compaction=self._execute_compaction,
            dispatch_event=self.dispatch_event,
            has_queued_messages=self.agent.has_queued_messages,
            before_compaction=self._before_compaction,
            after_compaction=self._after_compaction,
            record_runtime_exception=self.record_runtime_exception,
        )

    @property
    def is_compacting(self) -> bool:
        return self._runtime.is_compacting

    def clear_overflow_recovery_attempted(self) -> None:
        self._runtime.clear_overflow_recovery_attempted()

    async def maybe_compact_after_turn(
        self,
        assistant_message: AssistantMessage,
        *,
        compact_internal_fn: CompactInternalRunner | None = None,
        continue_run_fn: ContinueRun | None = None,
        is_context_overflow_fn: ContextOverflowPredicate = is_context_overflow,
    ) -> CompactionResult | None:
        return await self._runtime.maybe_compact_after_turn(
            assistant_message,
            compact_internal_fn=compact_internal_fn,
            continue_run_fn=continue_run_fn,
            is_context_overflow_fn=is_context_overflow_fn,
        )

    async def compact(
        self,
        *,
        reason: str,
        will_retry: bool,
        raise_on_error: bool = True,
        custom_instructions: str | None = None,
        compact_fn: CompactionFunction | None = None,
        prepare_compaction_fn: PrepareCompactionFunction | None = None,
    ) -> CompactionResult | None:
        executor = (
            self._execute_compaction
            if compact_fn is None
            else lambda preparation, instructions: self._execute_with(
                compact_fn, preparation, instructions
            )
        )
        preparation = (
            self._prepare_compaction
            if prepare_compaction_fn is None
            else lambda entries, keep_recent_tokens: prepare_compaction_fn(
                entries, keep_recent_tokens
            )
        )
        return await self._runtime.compact(
            reason=cast(CompactionReason, reason),
            will_retry=will_retry,
            raise_on_error=raise_on_error,
            custom_instructions=custom_instructions,
            execute_compaction=executor,
            prepare_compaction=preparation,
        )

    def _prepare_compaction(
        self,
        entries: list[object],
        keep_recent_tokens: int,
    ) -> CompactionPreparation:
        return self.prepare_compaction_fn(entries, keep_recent_tokens)

    async def _execute_compaction(
        self,
        preparation: CompactionPreparation,
        custom_instructions: str | None,
    ) -> CompactionResult:
        return await self._execute_with(
            self.compact_fn,
            preparation,
            custom_instructions,
        )

    async def _execute_with(
        self,
        compact_fn: CompactionFunction,
        preparation: CompactionPreparation,
        custom_instructions: str | None,
    ) -> CompactionResult:
        kwargs: dict[str, object] = {
            "preparation": preparation,
            "model": self.agent.model,
            "api_key": "",
            "headers": None,
            "signal": self.agent.signal,
        }
        if custom_instructions is not None:
            kwargs["custom_instructions"] = custom_instructions
        return await compact_fn(**kwargs)

    async def _before_compaction(
        self,
        request: CompactionHookRequest,
    ) -> CompactionHookDecision | None:
        extension_runner = self.get_extension_runner()
        if extension_runner is None:
            return None
        decision = await extension_runner.before_session_compact(
            SessionBeforeCompactEvent(
                reason=request.reason,
                cwd=str(self.session_manager.get_cwd()),
                custom_instructions=request.custom_instructions,
            )
        )
        if decision is not None and decision.cancel:
            self.sync_extension_diagnostics(phase="runtime")
            return CompactionHookDecision(cancel=True)
        result = getattr(decision, "compaction", None)
        return CompactionHookDecision(result=result) if result is not None else None

    async def _after_compaction(
        self,
        result: CompactionResult,
        record_id: str,
        from_hook: bool,
    ) -> None:
        extension_runner = self.get_extension_runner()
        if extension_runner is None:
            return
        await extension_runner.emit_event(
            {
                "type": "session_compact",
                "compaction": result,
                "compaction_entry": self.session_manager.get_entry(record_id),
                "from_extension": from_hook,
            },
            cwd=self.session_manager.get_cwd(),
        )

    def _refresh_agent_context(self) -> None:
        self.agent.state.set_messages(
            list(self.session_manager.build_session_context().messages)
        )


def _compaction_policy(settings: CompactionSettings) -> TranscriptCompactionPolicy:
    return TranscriptCompactionPolicy(
        enabled=settings.enabled,
        reserve_tokens=settings.reserve_tokens,
        compact_percent=settings.compact_percent,
        keep_recent_tokens=settings.keep_recent_tokens,
    )


__all__ = ["CompactionController"]
