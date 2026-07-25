"""Maintenance primitives for the optional Agent transcript profile.

The profile owns durable conversation facts.  This module owns the reusable
runtime calculations around those facts: context-budget observations and
automatic retry lifecycle.  Product code supplies settings, continuation, and
presentation/diagnostic adapters; it does not need to reimplement the state
machines.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Literal, Protocol

from loushang.agent.types import AgentMessage
from loushang.ai.types import AssistantMessage, ToolResultMessage, UserMessage
from loushang.harness.context.budget import calculate_compaction_budget
from loushang.harness.context.compaction import CompactionCoordinator
from loushang.harness.context.usage import ContextUsageEstimate
from loushang.harness.conversation import ConversationRecord
from loushang.harness.events import (
    CompactionReason,
    ContextCompactionCompleted,
    ContextCompactionStarted,
    RetryAttempt,
    RetryCompleted,
    RetryOutcome,
    RetryStarted,
    SessionRuntimeEventPayload,
)
from loushang.harness.runtime import CancellationController, CancellationSignal
from loushang.harness.runtime.retry import RetryCoordinator, RetryPolicy
from loushang.harness.transcript.kinds import (
    AGENT_MESSAGE_KIND,
    CONTEXT_COMPACTION_CHECKPOINT_KIND,
)
from loushang.harness.transcript.types import AgentTranscriptRecord

ContextUsageSource = Literal[
    "assistant_usage", "estimated_from_last_usage", "estimated", "unknown"
]


@dataclass(frozen=True)
class ContextUsageSnapshot:
    """One context-budget observation over an Agent transcript branch."""

    tokens: int | None
    context_window: int | None
    reserve_tokens: int
    compact_percent: float = 100.0
    keep_recent_tokens: int | None = None
    percent_threshold_tokens: int | None = None
    reserve_threshold_tokens: int | None = None
    threshold_tokens: int | None = None
    threshold_reason: Literal["compact_percent", "reserve_tokens"] | None = None
    percent: float | None = None
    source: ContextUsageSource = "unknown"
    last_usage_index: int | None = None
    stale_after_compaction: bool = False
    compactable: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class CompactionDecision:
    """The profile-neutral outcome of checking one context budget."""

    action: Literal["none", "threshold", "overflow"]
    usage: ContextUsageSnapshot
    will_retry: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class CompactionResult:
    """A strategy-produced summary ready to become a transcript checkpoint."""

    summary: str
    first_kept_entry_id: str
    tokens_before: int
    details: object | None = None


@dataclass(frozen=True)
class CompactionStatus:
    is_compacting: bool
    is_branch_summarizing: bool = False
    last_reason: str | None = None
    last_result: CompactionResult | None = None
    last_error: str | None = None
    aborted: bool = False


@dataclass(frozen=True)
class CompactionPlan:
    previous_compaction_id: str | None
    previous_first_kept_entry_id: str | None
    first_kept_entry_id: str
    summarized_entry_ids: tuple[str, ...]
    turn_prefix_entry_ids: tuple[str, ...]
    kept_entry_ids: tuple[str, ...]
    is_split_turn: bool
    tokens_before: int
    keep_recent_tokens: int


@dataclass(frozen=True)
class CompactionPreparation:
    first_kept_entry_id: str
    messages_to_summarize: list[AgentMessage]
    turn_prefix_messages: list[AgentMessage]
    is_split_turn: bool
    tokens_before: int
    previous_summary: str | None = None
    details: object | None = None
    plan: CompactionPlan | None = None


@dataclass(frozen=True)
class TranscriptCompactionPolicy:
    """Product-selected automatic-compaction policy values."""

    enabled: bool
    reserve_tokens: int
    compact_percent: float = 100.0
    keep_recent_tokens: int | None = None


_NON_RETRYABLE_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"requires an api key",
        r"\bapi[-_ ]?key\b",
        r"authorization",
        r"authentication",
        r"\bunauthorized\b",
        r"\bforbidden\b",
        r"\b401\b",
        r"\b403\b",
        r"access[_ -]?terminated",
        r"access.?denied",
        r"permission.?denied",
        r"currently only available",
    )
)

_RETRYABLE_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"overloaded",
        r"provider.?returned.?error",
        r"rate.?limit",
        r"too many requests",
        r"\b429\b",
        r"\b500\b",
        r"\b502\b",
        r"\b503\b",
        r"\b504\b",
        r"service.?unavailable",
        r"server.?error",
        r"internal.?error",
        r"network.?error",
        r"network.*connection.*lost",
        r"connection.?error",
        r"connection.?refused",
        r"connection.*lost",
        r"fetch failed",
        r"upstream.?connect",
        r"socket hang up",
        r"ended without",
        r"timed? out",
        r"timeout",
        r"terminated",
        r"retry delay",
    )
)

RetrySettingsProvider = Callable[[], RetryPolicy]
EventDispatcher = Callable[[SessionRuntimeEventPayload], Awaitable[None]]
ContinueRun = Callable[[], Awaitable[None]]
RuntimeExceptionRecorder = Callable[..., None]
RetrySleeper = Callable[[int, CancellationSignal], Awaitable[None]]
WaitForIdle = Callable[[], Awaitable[None]]
MessageProvider = Callable[[], list[AgentMessage]]
MessageSetter = Callable[[list[AgentMessage]], None]
ContextWindowProvider = Callable[[], int | None]
ContextOverflowPredicate = Callable[[AssistantMessage, int], bool]


class AgentTranscriptRetryRuntime:
    """Run retry policy against one Agent transcript's live message state."""

    def __init__(
        self,
        *,
        get_policy: RetrySettingsProvider,
        get_messages: MessageProvider,
        set_messages: MessageSetter,
        get_context_window: ContextWindowProvider,
        dispatch_event: EventDispatcher,
        continue_run: ContinueRun,
        record_runtime_exception: RuntimeExceptionRecorder,
        sleep_for_retry: RetrySleeper,
        is_context_overflow_fn: ContextOverflowPredicate,
        wait_for_idle: WaitForIdle | None = None,
    ) -> None:
        self._get_policy = get_policy
        self._get_messages = get_messages
        self._set_messages = set_messages
        self._get_context_window = get_context_window
        self._dispatch_event = dispatch_event
        self._record_runtime_exception = record_runtime_exception
        self._is_context_overflow = is_context_overflow_fn
        self._coordinator = RetryCoordinator(
            create_cancel_handle=CancellationController,
            cancel=lambda controller: controller.abort(),
            delay=lambda delay_ms, controller: sleep_for_retry(
                delay_ms, controller.signal
            ),
            continue_run=continue_run,
            on_started=self._on_started,
            on_finished=self._on_finished,
            wait_for_idle=wait_for_idle,
        )

    @property
    def attempt(self) -> int:
        return self._coordinator.attempt

    @attempt.setter
    def attempt(self, value: int) -> None:
        self._coordinator.attempt = value

    @property
    def retry_future(self) -> asyncio.Future[None] | object | None:
        return self._coordinator.future

    @retry_future.setter
    def retry_future(self, value: asyncio.Future[None] | object | None) -> None:
        self._coordinator.future = value

    @property
    def is_retrying(self) -> bool:
        return self._coordinator.is_retrying

    @property
    def cancel_handle(self) -> CancellationController | None:
        return self._coordinator.cancel_handle

    @cancel_handle.setter
    def cancel_handle(self, value: CancellationController | None) -> None:
        self._coordinator.cancel_handle = value

    def abort(self) -> None:
        self._coordinator.abort()

    async def wait(self) -> None:
        await self._coordinator.wait()

    def ensure_future(self) -> asyncio.Future[None]:
        return self._coordinator.ensure_waiter()

    async def finish(
        self,
        *,
        success: bool,
        attempt: int,
        final_error: str | None = None,
    ) -> None:
        await self._coordinator.finish(
            RetryOutcome(
                success=success,
                attempt=attempt,
                error=final_error,
                cancelled=final_error == "Retry cancelled",
            )
        )

    async def finish_success_if_needed(
        self, assistant_message: AssistantMessage
    ) -> None:
        if assistant_message.stop_reason != "error" and self.attempt > 0:
            await self.finish(success=True, attempt=self.attempt)

    def should_prepare_retry(self, assistant_message: AssistantMessage) -> bool:
        return self._get_policy().enabled and self.is_retryable_error(assistant_message)

    def is_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        return is_retryable_assistant_error(
            assistant_message,
            context_window=self._get_context_window() or 0,
            is_context_overflow_fn=self._is_context_overflow,
        )

    async def handle_retryable_error(self, assistant_message: AssistantMessage) -> bool:
        return await self._coordinator.retry(
            assistant_message.error_message or "",
            policy=self._get_policy(),
            before_retry=self._remove_failed_assistant,
        )

    async def _on_started(self, attempt: RetryAttempt) -> None:
        await self._dispatch_event(RetryStarted(attempt=attempt))

    async def _on_finished(self, outcome: RetryOutcome) -> None:
        final_error = (
            ("Retry cancelled" if outcome.cancelled else outcome.error)
            if not outcome.success
            else None
        )
        if final_error is not None:
            self._record_runtime_exception(
                code="retry_cancelled" if outcome.cancelled else "retry_failed",
                exc=final_error,
            )
        await self._dispatch_event(
            RetryCompleted(
                outcome=RetryOutcome(
                    success=outcome.success,
                    attempt=outcome.attempt,
                    error=final_error,
                    cancelled=outcome.cancelled,
                )
            )
        )

    def _remove_failed_assistant(self) -> None:
        messages = self._get_messages()
        if messages and getattr(messages[-1], "role", None) == "assistant":
            self._set_messages(messages[:-1])


class TranscriptCompactionStore(Protocol):
    """The narrow transcript mutation surface required by maintenance."""

    def get_branch(self) -> list[AgentTranscriptRecord]: ...

    async def append_compaction(
        self,
        summary: str,
        first_kept_entry_id: str,
        tokens_before: int,
        details: object | None = None,
        from_hook: bool | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class CompactionHookRequest:
    reason: CompactionReason
    custom_instructions: str | None


@dataclass(frozen=True)
class CompactionHookDecision:
    """Product adapter result for one optional pre-compaction interception."""

    cancel: bool = False
    result: CompactionResult | None = None


CompactionPolicyProvider = Callable[[], TranscriptCompactionPolicy]
ModelProvider = Callable[[], object | None]
ContextMessagesProvider = Callable[[], list[AgentMessage]]
ContextRefresher = Callable[[], None]
PreparationProvider = Callable[
    [list[AgentTranscriptRecord], int], CompactionPreparation
]
CompactionExecutor = Callable[
    [CompactionPreparation, str | None], Awaitable[CompactionResult]
]
CompactionHook = Callable[
    [CompactionHookRequest], Awaitable[CompactionHookDecision | None]
]
CompactionCommitObserver = Callable[[CompactionResult, str, bool], Awaitable[None]]
CompactionRunner = Callable[..., Awaitable[CompactionResult | None]]
HasQueuedMessages = Callable[[], bool]


def _noop_record_runtime_exception(*, code: str, exc: Exception | str) -> None:
    del code, exc


class AgentTranscriptCompactionRuntime:
    """Own compaction lifecycle around a transcript and product strategy ports."""

    def __init__(
        self,
        *,
        transcript: TranscriptCompactionStore,
        get_policy: CompactionPolicyProvider,
        get_model: ModelProvider,
        get_context_messages: ContextMessagesProvider,
        refresh_context: ContextRefresher,
        prepare_compaction: PreparationProvider,
        execute_compaction: CompactionExecutor,
        dispatch_event: EventDispatcher,
        has_queued_messages: HasQueuedMessages,
        before_compaction: CompactionHook | None = None,
        after_compaction: CompactionCommitObserver | None = None,
        record_runtime_exception: RuntimeExceptionRecorder = _noop_record_runtime_exception,
    ) -> None:
        self._transcript = transcript
        self._get_policy = get_policy
        self._get_model = get_model
        self._get_context_messages = get_context_messages
        self._refresh_context = refresh_context
        self._prepare_compaction = prepare_compaction
        self._execute_compaction = execute_compaction
        self._dispatch_event = dispatch_event
        self._has_queued_messages = has_queued_messages
        self._before_compaction = before_compaction
        self._after_compaction = after_compaction
        self._record_runtime_exception = record_runtime_exception
        self._lifecycle: CompactionCoordinator[CompactionResult] = (
            CompactionCoordinator()
        )
        self._overflow_recovery_attempted = False

    @property
    def is_compacting(self) -> bool:
        return self._lifecycle.is_compacting

    def get_status(self) -> CompactionStatus:
        status = self._lifecycle.get_status()
        return CompactionStatus(
            is_compacting=status.is_compacting,
            last_reason=status.last_reason,
            last_result=status.last_result,
            last_error=status.last_error,
            aborted=status.aborted,
        )

    def abort(self) -> None:
        self._lifecycle.abort()

    def clear_overflow_recovery_attempted(self) -> None:
        self._overflow_recovery_attempted = False

    async def maybe_compact_after_turn(
        self,
        assistant_message: AssistantMessage,
        *,
        compact_internal_fn: CompactionRunner | None = None,
        continue_run_fn: ContinueRun | None = None,
        is_context_overflow_fn: ContextOverflowPredicate | None = None,
    ) -> CompactionResult | None:
        policy = self._get_policy()
        if not policy.enabled:
            return None
        context_window = model_context_window(self._get_model()) or 0
        if context_window <= 0:
            return None
        branch = self._transcript.get_branch()
        latest_compaction = latest_compaction_entry(branch)
        if latest_compaction is not None and _message_is_before_or_at_entry(
            assistant_message, latest_compaction
        ):
            return None

        run_compact = compact_internal_fn or self.compact
        if is_context_overflow_fn is not None and is_context_overflow_fn(
            assistant_message, context_window
        ):
            if self._overflow_recovery_attempted:
                message = (
                    "Context overflow recovery failed after one compact-and-retry attempt. "
                    "Try reducing context or switching to a larger-context model."
                )
                usage = _snapshot_payload(self.build_usage_snapshot(policy))
                await self._dispatch_event(
                    ContextCompactionCompleted(
                        reason="overflow",
                        result=None,
                        aborted=False,
                        will_retry=True,
                        error_message=message,
                        usage_before=usage,
                        usage_after=usage,
                    )
                )
                return None
            self._overflow_recovery_attempted = True
            result = await run_compact(
                reason="overflow", will_retry=True, raise_on_error=False
            )
            if result is not None and continue_run_fn is not None:
                asyncio.ensure_future(continue_run_fn())
            return result

        context_messages = self._get_context_messages()
        if not any(message is assistant_message for message in context_messages):
            context_messages.append(assistant_message)
        decision = build_threshold_compaction_decision(
            context_messages,
            branch,
            self._get_model(),
            enabled=policy.enabled,
            reserve_tokens=policy.reserve_tokens,
            compact_percent=policy.compact_percent,
            keep_recent_tokens=policy.keep_recent_tokens,
        )
        if decision.usage.tokens is None or decision.action != "threshold":
            return None
        result = await run_compact(
            reason="threshold", will_retry=False, raise_on_error=False
        )
        if (
            result is not None
            and continue_run_fn is not None
            and self._has_queued_messages()
        ):
            asyncio.ensure_future(continue_run_fn())
        return result

    async def compact(
        self,
        *,
        reason: CompactionReason,
        will_retry: bool,
        raise_on_error: bool = True,
        custom_instructions: str | None = None,
        execute_compaction: CompactionExecutor | None = None,
        prepare_compaction: PreparationProvider | None = None,
    ) -> CompactionResult | None:
        policy = self._get_policy()
        usage_before = _snapshot_payload(self.build_usage_snapshot(policy))
        await self._dispatch_event(
            ContextCompactionStarted(reason=reason, usage=usage_before)
        )
        try:
            result = await self._lifecycle.run(
                lambda: self._execute(
                    reason=reason,
                    custom_instructions=custom_instructions,
                    prepare_compaction=prepare_compaction or self._prepare_compaction,
                    execute_compaction=execute_compaction or self._execute_compaction,
                    policy=policy,
                ),
                reason=reason,
            )
        except Exception as exc:
            aborted = is_compaction_aborted(exc)
            if not aborted:
                self._record_runtime_exception(code="compaction_failed", exc=exc)
            await self._dispatch_event(
                ContextCompactionCompleted(
                    reason=reason,
                    result=None,
                    aborted=aborted,
                    will_retry=will_retry,
                    usage_before=usage_before,
                    usage_after=_snapshot_payload(self.build_usage_snapshot(policy)),
                    error_message=None if aborted else f"Compaction failed: {exc}",
                )
            )
            if raise_on_error:
                raise
            return None

        await self._dispatch_event(
            ContextCompactionCompleted(
                reason=reason,
                result=asdict(result),
                aborted=False,
                will_retry=will_retry,
                usage_before=usage_before,
                usage_after=_snapshot_payload(self.build_usage_snapshot(policy)),
            )
        )
        return result

    def build_usage_snapshot(
        self, policy: TranscriptCompactionPolicy | None = None
    ) -> ContextUsageSnapshot:
        active_policy = policy or self._get_policy()
        return build_context_usage_snapshot(
            self._get_context_messages(),
            self._transcript.get_branch(),
            self._get_model(),
            reserve_tokens=active_policy.reserve_tokens,
            compact_percent=active_policy.compact_percent,
            keep_recent_tokens=active_policy.keep_recent_tokens,
        )

    async def _execute(
        self,
        *,
        reason: CompactionReason,
        custom_instructions: str | None,
        prepare_compaction: PreparationProvider,
        execute_compaction: CompactionExecutor,
        policy: TranscriptCompactionPolicy,
    ) -> CompactionResult:
        preparation = prepare_compaction(
            self._transcript.get_branch(),
            policy.keep_recent_tokens or 0,
        )
        if (
            not preparation.messages_to_summarize
            and not preparation.turn_prefix_messages
        ):
            raise RuntimeError("Nothing to compact (session too small)")

        result: CompactionResult | None = None
        from_hook = False
        if self._before_compaction is not None:
            decision = await self._before_compaction(
                CompactionHookRequest(
                    reason=reason,
                    custom_instructions=custom_instructions,
                )
            )
            if decision is not None and decision.cancel:
                raise RuntimeError("Compaction cancelled")
            if decision is not None and decision.result is not None:
                result = decision.result
                from_hook = True

        if result is None:
            result = await execute_compaction(preparation, custom_instructions)
        result = _with_preparation_details(result, preparation)
        record_id = await self._transcript.append_compaction(
            result.summary,
            result.first_kept_entry_id,
            result.tokens_before,
            details=result.details,
            from_hook=from_hook,
        )
        if self._after_compaction is not None:
            await self._after_compaction(result, record_id, from_hook)
        self._refresh_context()
        return result


def calculate_context_tokens(usage: object) -> int:
    """Extract total tokens from stable AI usage values or their JSON form."""

    total_tokens = _usage_value(usage, "totalTokens", "total_tokens")
    if isinstance(total_tokens, int) and total_tokens > 0:
        return total_tokens
    return sum(
        _integer_usage_value(_usage_value(usage, *keys))
        for keys in (
            ("input",),
            ("output",),
            ("cacheRead", "cache_read"),
            ("cacheWrite", "cache_write"),
        )
    )


def estimate_context_tokens(messages: Sequence[AgentMessage]) -> ContextUsageEstimate:
    """Estimate current context using the latest completed assistant usage."""

    sequence = list(messages)
    last_usage = _last_assistant_usage_info(sequence)
    if last_usage is None:
        estimated = sum(estimate_message_tokens(message) for message in sequence)
        return ContextUsageEstimate(
            tokens=estimated,
            usage_tokens=0,
            trailing_tokens=estimated,
            last_usage_index=None,
        )

    usage, usage_index = last_usage
    usage_tokens = calculate_context_tokens(usage)
    trailing_tokens = sum(
        estimate_message_tokens(message) for message in sequence[usage_index + 1 :]
    )
    return ContextUsageEstimate(
        tokens=usage_tokens + trailing_tokens,
        usage_tokens=usage_tokens,
        trailing_tokens=trailing_tokens,
        last_usage_index=usage_index,
    )


def current_context_usage(
    messages: Sequence[AgentMessage],
    branch_entries: Sequence[object],
    model: object | None,
) -> tuple[int | None, int | None, float | None]:
    snapshot = build_context_usage_snapshot(
        messages, branch_entries, model, reserve_tokens=0
    )
    return snapshot.tokens, snapshot.context_window, snapshot.percent


def build_context_usage_snapshot(
    messages: Sequence[AgentMessage],
    branch_entries: Sequence[object],
    model: object | None,
    *,
    reserve_tokens: int,
    compact_percent: float = 100.0,
    keep_recent_tokens: int | None = None,
) -> ContextUsageSnapshot:
    context_window = model_context_window(model)
    if context_window is None:
        return ContextUsageSnapshot(
            tokens=None,
            context_window=None,
            reserve_tokens=reserve_tokens,
            compact_percent=compact_percent,
            keep_recent_tokens=keep_recent_tokens,
            threshold_tokens=None,
            threshold_reason=None,
            percent=None,
            source="unknown",
            last_usage_index=None,
            stale_after_compaction=False,
            compactable=False,
            reason="unknown_context_window",
        )

    budget = calculate_compaction_budget(
        context_window=context_window,
        compact_percent=compact_percent,
        reserve_tokens=reserve_tokens,
    )
    latest_compaction = latest_compaction_entry(branch_entries)
    if latest_compaction is not None and not has_post_compaction_usage(
        branch_entries, latest_compaction
    ):
        return ContextUsageSnapshot(
            tokens=None,
            context_window=context_window,
            reserve_tokens=reserve_tokens,
            compact_percent=budget.compact_percent,
            keep_recent_tokens=keep_recent_tokens,
            percent_threshold_tokens=budget.percent_threshold_tokens,
            reserve_threshold_tokens=budget.reserve_threshold_tokens,
            threshold_tokens=budget.threshold_tokens,
            threshold_reason=budget.threshold_reason,
            percent=None,
            source="unknown",
            last_usage_index=None,
            stale_after_compaction=True,
            compactable=False,
            reason="stale_usage_after_compaction",
        )

    estimate = estimate_context_tokens(messages) if messages else None
    tokens = estimate.tokens if estimate is not None else 0
    last_usage_index = estimate.last_usage_index if estimate is not None else None
    if estimate is None or last_usage_index is None:
        source: ContextUsageSource = "estimated"
    elif estimate.trailing_tokens > 0:
        source = "estimated_from_last_usage"
    else:
        source = "assistant_usage"
    compactable = tokens > budget.threshold_tokens
    return ContextUsageSnapshot(
        tokens=tokens,
        context_window=context_window,
        reserve_tokens=reserve_tokens,
        compact_percent=budget.compact_percent,
        keep_recent_tokens=keep_recent_tokens,
        percent_threshold_tokens=budget.percent_threshold_tokens,
        reserve_threshold_tokens=budget.reserve_threshold_tokens,
        threshold_tokens=budget.threshold_tokens,
        threshold_reason=budget.threshold_reason,
        percent=(tokens / context_window) * 100,
        source=source,
        last_usage_index=last_usage_index,
        stale_after_compaction=False,
        compactable=compactable,
        reason="threshold" if compactable else None,
    )


def build_threshold_compaction_decision(
    messages: Sequence[AgentMessage],
    branch_entries: Sequence[object],
    model: object | None,
    *,
    enabled: bool,
    reserve_tokens: int,
    compact_percent: float = 100.0,
    keep_recent_tokens: int | None = None,
) -> CompactionDecision:
    snapshot = build_context_usage_snapshot(
        messages,
        branch_entries,
        model,
        reserve_tokens=reserve_tokens,
        compact_percent=compact_percent,
        keep_recent_tokens=keep_recent_tokens,
    )
    if enabled and snapshot.compactable:
        return CompactionDecision(
            action="threshold",
            usage=snapshot,
            will_retry=False,
            reason=snapshot.reason,
        )
    return CompactionDecision(
        action="none",
        usage=snapshot,
        will_retry=False,
        reason=snapshot.reason,
    )


def model_context_window(model: object | None) -> int | None:
    capabilities: object | None = getattr(model, "capabilities", None)
    raw_context_window: object | None = getattr(capabilities, "context_window", None)
    if raw_context_window is None:
        raw_context_window = getattr(model, "context_window", None)
    return _positive_int(raw_context_window)


def latest_compaction_entry(
    entries: Sequence[object],
) -> ConversationRecord[object] | None:
    for entry in reversed(entries):
        if (
            isinstance(entry, ConversationRecord)
            and entry.kind == CONTEXT_COMPACTION_CHECKPOINT_KIND
        ):
            return entry
    return None


def has_post_compaction_usage(
    entries: Sequence[object], compaction: ConversationRecord[object]
) -> bool:
    try:
        compaction_index = list(entries).index(compaction)
    except ValueError:
        return False
    for entry in reversed(entries[compaction_index + 1 :]):
        if (
            not isinstance(entry, ConversationRecord)
            or entry.kind != AGENT_MESSAGE_KIND
        ):
            continue
        message = entry.payload
        if not isinstance(message, AssistantMessage):
            continue
        if message.stop_reason in {"aborted", "error"}:
            return False
        return calculate_context_tokens(message.usage) > 0
    return False


def is_compaction_aborted(exc: Exception) -> bool:
    return (
        str(exc) == "Compaction cancelled" or getattr(exc, "name", None) == "AbortError"
    )


def _message_is_before_or_at_entry(
    message: AssistantMessage, entry: ConversationRecord[object]
) -> bool:
    entry_timestamp = _entry_timestamp_ms(entry.created_at)
    return entry_timestamp is not None and message.timestamp <= entry_timestamp


def _entry_timestamp_ms(timestamp: str) -> float | None:
    try:
        return (
            datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() * 1000
        )
    except ValueError:
        return None


def _snapshot_payload(snapshot: ContextUsageSnapshot) -> dict[str, Any]:
    return asdict(snapshot)


def _with_preparation_details(
    result: CompactionResult,
    preparation: CompactionPreparation,
) -> CompactionResult:
    details = _merge_preparation_result_details(preparation.details, result.details)
    return result if details == result.details else replace(result, details=details)


def _merge_preparation_result_details(
    preparation_details: object | None,
    result_details: object | None,
) -> object | None:
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


def is_retryable_assistant_error(
    message: AssistantMessage,
    *,
    context_window: int,
    is_context_overflow_fn: ContextOverflowPredicate,
) -> bool:
    if message.stop_reason != "error" or not message.error_message:
        return False
    if is_context_overflow_fn(message, context_window):
        return False
    if any(
        pattern.search(message.error_message)
        for pattern in _NON_RETRYABLE_ERROR_PATTERNS
    ):
        return False
    return any(
        pattern.search(message.error_message) for pattern in _RETRYABLE_ERROR_PATTERNS
    )


def _usage_value(usage: object, *keys: str) -> object | None:
    if isinstance(usage, Mapping):
        for key in keys:
            value = usage.get(key)
            if value is not None:
                return value
        return None
    for key in keys:
        if hasattr(usage, key):
            value = getattr(usage, key)
            if value is not None:
                return value
    return None


def _integer_usage_value(value: object | None) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _positive_int(value: object | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float | str):
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _last_assistant_usage_info(
    messages: Sequence[AgentMessage],
) -> tuple[object, int] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, AssistantMessage) and message.stop_reason not in (
            "aborted",
            "error",
        ):
            return message.usage, index
    return None


def estimate_message_tokens(message: AgentMessage) -> int:
    chars = 0
    if isinstance(message, UserMessage):
        if isinstance(message.content, str):
            chars = len(message.content)
        else:
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    chars += len(str(getattr(block, "text", "")))
                elif getattr(block, "type", None) == "image":
                    chars += 4_800
        return (chars + 3) // 4
    if isinstance(message, AssistantMessage):
        for assistant_block in message.content:
            block_type = getattr(assistant_block, "type", None)
            if block_type == "text":
                chars += len(str(getattr(assistant_block, "text", "")))
            elif block_type == "thinking":
                chars += len(str(getattr(assistant_block, "thinking", "")))
            elif block_type == "toolCall":
                chars += len(str(getattr(assistant_block, "name", ""))) + len(
                    str(getattr(assistant_block, "arguments", ""))
                )
            elif block_type == "image":
                chars += 4_800
        return (chars + 3) // 4
    if isinstance(message, ToolResultMessage):
        for block in message.content:
            if getattr(block, "type", None) == "text":
                chars += len(str(getattr(block, "text", "")))
            elif getattr(block, "type", None) == "image":
                chars += 4_800
        return (chars + 3) // 4
    return 0


__all__ = [
    "AgentTranscriptCompactionRuntime",
    "AgentTranscriptRetryRuntime",
    "CompactionHookDecision",
    "CompactionHookRequest",
    "CompactionDecision",
    "CompactionPlan",
    "CompactionPreparation",
    "CompactionResult",
    "CompactionStatus",
    "ContextUsageSnapshot",
    "TranscriptCompactionStore",
    "TranscriptCompactionPolicy",
    "build_context_usage_snapshot",
    "build_threshold_compaction_decision",
    "calculate_context_tokens",
    "current_context_usage",
    "estimate_context_tokens",
    "estimate_message_tokens",
    "has_post_compaction_usage",
    "is_retryable_assistant_error",
    "is_compaction_aborted",
    "latest_compaction_entry",
    "model_context_window",
]
