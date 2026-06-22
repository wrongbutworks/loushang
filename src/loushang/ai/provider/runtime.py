from __future__ import annotations

import asyncio
import inspect
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.options import RetryOptions
from loushang.ai.provider.cancellation import is_signal_cancelled, wait_signal_cancelled
from loushang.ai.provider.errors import (
    normalize_provider_error,
    provider_error_info_from_raw,
    provider_error_part,
)
from loushang.ai.provider.resolution import ResolvedRequest
from loushang.ai.trace import emit_trace

RawPartSource = Callable[[], AsyncIterator[RawPart] | Any]
Sleep = Callable[[float], Awaitable[object]]
Jitter = Callable[[], float]

_DEFAULT_MAX_RETRY_DELAY_SECONDS = 30.0
_INITIAL_RETRY_DELAY_SECONDS = 0.25
_VISIBLE_RAW_PART_TYPES = frozenset(
    {
        "text_delta",
        "thinking_delta",
        "thinking_signature_delta",
        "redacted_thinking",
        "tool_call_start",
        "tool_call_args_delta",
        "tool_call_done",
        "tool_call_thought_signature",
        "image_part",
    }
)
_TERMINAL_RAW_PART_TYPES = frozenset(
    {"response_done", "response_error", "aborted"}
)


class _RuntimeCancelled(Exception):
    pass


def start_provider_runtime(
    raw_parts: RawPartSource,
    *,
    model,
    options,
    request: ResolvedRequest,
    _sleep: Sleep = asyncio.sleep,
    _jitter: Jitter = random.random,
) -> AssistantMessageEventStream:
    stream = AssistantMessageEventStream()
    assembler = RawAssembler(
        stream=stream,
        api=request.api,
        provider=getattr(model, "provider_id", request.provider),
        model=getattr(model, "id", None) or request.upstream_model_id or "",
        pricing=getattr(model, "pricing", None),
    )

    async def _run() -> None:
        signals = _cancellation_signals(options)
        cancellation_task = _create_cancellation_task(signals)
        if _signals_cancelled(signals):
            await assembler.emit({"type": "aborted"})
            return
        try:
            max_attempts = _retry_max_attempts(options)
            attempt = 1
            while attempt <= max_attempts:
                pending: list[RawPart] = []
                visible_output_started = False
                retry_next_attempt = False
                source = None
                try:
                    source = raw_parts()
                    if inspect.isawaitable(source):
                        source = await _await_or_cancel(source, cancellation_task)
                    while True:
                        try:
                            part = await _next_raw_part(source, cancellation_task)
                        except StopAsyncIteration:
                            break

                        if _signals_cancelled(signals):
                            raise _RuntimeCancelled

                        if (
                            part["type"] == "response_error"
                            and not visible_output_started
                            and attempt < max_attempts
                            and _retryable_response_error_part(
                                part,
                                request=request,
                                model=model,
                            )
                        ):
                            await _sleep_before_retry(
                                options=options,
                                attempt=attempt,
                                max_attempts=max_attempts,
                                retry_after_seconds=_retry_after_seconds_from_part(part),
                                reason=_retry_reason_from_part(part, request, model),
                                sleep=_sleep,
                                jitter=_jitter,
                                cancellation_task=cancellation_task,
                            )
                            retry_next_attempt = True
                            break

                        if part["type"] in _VISIBLE_RAW_PART_TYPES:
                            await _flush_pending(assembler, pending)
                            visible_output_started = True
                            await assembler.emit(part)
                            continue

                        if (
                            visible_output_started
                            or part["type"] in _TERMINAL_RAW_PART_TYPES
                        ):
                            await _flush_pending(assembler, pending)
                            await assembler.emit(part)
                            if part["type"] in _TERMINAL_RAW_PART_TYPES:
                                return
                            continue

                        pending.append(part)

                    if retry_next_attempt:
                        attempt += 1
                        continue
                    await _flush_pending(assembler, pending)
                    await assembler.emit({"type": "response_done"})
                    return
                except _RuntimeCancelled:
                    await _flush_pending(assembler, pending)
                    await assembler.emit({"type": "aborted"})
                    return
                except Exception as error:
                    if _signals_cancelled(signals):
                        await _flush_pending(assembler, pending)
                        await assembler.emit({"type": "aborted"})
                        return
                    if (
                        not visible_output_started
                        and attempt < max_attempts
                        and _retryable_exception(error, source=request.api)
                    ):
                        await _sleep_before_retry(
                            options=options,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            retry_after_seconds=_retry_after_seconds_from_exception(error),
                            reason=_retry_reason_from_exception(error, request.api),
                            sleep=_sleep,
                            jitter=_jitter,
                            cancellation_task=cancellation_task,
                        )
                        attempt += 1
                        continue
                    await _flush_pending(assembler, pending)
                    await assembler.emit(
                        cast(RawPart, provider_error_part(error, source=request.api))
                    )
                    return
                finally:
                    await _close_source(source)
        finally:
            await _cancel_task(cancellation_task)

    stream.attach_task(asyncio.create_task(_run()))
    return stream


async def _flush_pending(assembler: RawAssembler, pending: list[RawPart]) -> None:
    while pending:
        await assembler.emit(pending.pop(0))


def _cancellation_signals(options: object | None) -> tuple[object, ...]:
    if options is None:
        return ()
    signals: list[object] = []
    for name in ("cancellation", "signal"):
        signal = getattr(options, name, None)
        if signal is not None and any(signal is existing for existing in signals):
            continue
        if signal is not None:
            signals.append(signal)
    return tuple(signals)


def _signals_cancelled(signals: tuple[object, ...]) -> bool:
    return any(is_signal_cancelled(signal) for signal in signals)


def _create_cancellation_task(
    signals: tuple[object, ...],
) -> asyncio.Task[None] | None:
    if not signals:
        return None
    return asyncio.create_task(_wait_any_signal_cancelled(signals))


async def _wait_any_signal_cancelled(signals: tuple[object, ...]) -> None:
    if _signals_cancelled(signals):
        return
    tasks = [
        asyncio.create_task(wait_signal_cancelled(signal))
        for signal in signals
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            await task
        for task in pending:
            with suppress(asyncio.CancelledError):
                await task
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _await_or_cancel(awaitable, cancellation_task: asyncio.Task[None] | None):
    if cancellation_task is None:
        return await awaitable
    if cancellation_task.done():
        raise _RuntimeCancelled
    task = asyncio.ensure_future(awaitable)
    try:
        done, pending = await asyncio.wait(
            {task, cancellation_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
    except BaseException:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise
    if cancellation_task in done:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise _RuntimeCancelled
    for pending_task in pending:
        if pending_task is not cancellation_task:
            pending_task.cancel()
    return await task


async def _next_raw_part(source, cancellation_task: asyncio.Task[None] | None):
    iterator = source.__aiter__() if hasattr(source, "__aiter__") else source
    return await _await_or_cancel(iterator.__anext__(), cancellation_task)


async def _close_source(source) -> None:
    if source is None:
        return
    for name in ("aclose", "close"):
        close = getattr(source, name, None)
        if not callable(close):
            continue
        result = close()
        if inspect.isawaitable(result):
            await result
        return


async def _cancel_task(task: asyncio.Task[object] | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _retry_max_attempts(options: object | None) -> int:
    if options is None:
        return 1
    retry = getattr(options, "retry", None)
    if isinstance(retry, RetryOptions):
        return max(1, retry.max_attempts)
    retries = getattr(options, "retries", None)
    if isinstance(retries, int) and not isinstance(retries, bool):
        return max(1, retries + 1)
    return 1


def _retry_max_delay_seconds(options: object | None) -> float:
    if options is None:
        return _DEFAULT_MAX_RETRY_DELAY_SECONDS
    retry = getattr(options, "retry", None)
    if isinstance(retry, RetryOptions):
        return max(0.0, float(retry.max_delay_seconds))
    max_delay_ms = getattr(options, "max_retry_delay_ms", None)
    if isinstance(max_delay_ms, int) and not isinstance(max_delay_ms, bool):
        return max(0.0, max_delay_ms / 1000.0)
    return _DEFAULT_MAX_RETRY_DELAY_SECONDS


def _retryable_exception(error: Exception, *, source: str) -> bool:
    return normalize_provider_error(error, source=source).info.retryable


def _retryable_response_error_part(
    part: RawPart,
    *,
    request: ResolvedRequest,
    model,
) -> bool:
    try:
        error_info = provider_error_info_from_raw(
            cast(Mapping[str, object], part),
            source=request.api,
            provider=request.provider,
            model=getattr(model, "id", None),
        )
    except Exception:
        return False
    return error_info.retryable


async def _sleep_before_retry(
    *,
    options,
    attempt: int,
    max_attempts: int,
    retry_after_seconds: float | None,
    reason: dict[str, object],
    sleep: Sleep,
    jitter: Jitter,
    cancellation_task: asyncio.Task[None] | None,
) -> None:
    delay_seconds = _retry_delay_seconds(
        attempt=attempt,
        options=options,
        retry_after_seconds=retry_after_seconds,
        jitter=jitter,
    )
    emit_trace(
        options,
        {
            "type": "runtime:retry",
            "attempt": attempt + 1,
            "maxAttempts": max_attempts,
            "delayMs": int(delay_seconds * 1000),
            **reason,
        },
    )
    if delay_seconds > 0:
        await _await_or_cancel(sleep(delay_seconds), cancellation_task)


def _retry_delay_seconds(
    *,
    attempt: int,
    options,
    retry_after_seconds: float | None,
    jitter: Jitter,
) -> float:
    max_delay = _retry_max_delay_seconds(options)
    if max_delay <= 0:
        return 0.0
    backoff = min(max_delay, _INITIAL_RETRY_DELAY_SECONDS * (2 ** max(0, attempt - 1)))
    jitter_ratio = min(1.0, max(0.0, float(jitter())))
    delay = backoff + (backoff * 0.25 * jitter_ratio)
    if retry_after_seconds is not None:
        delay = max(delay, retry_after_seconds)
    return min(max_delay, delay)


def _retry_after_seconds_from_exception(error: Exception) -> float | None:
    headers = getattr(error, "headers", None)
    if headers is None:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
    return _retry_after_seconds_from_headers(headers)


def _retry_after_seconds_from_part(part: RawPart) -> float | None:
    for key in ("retryAfter", "retry_after"):
        value = cast(Mapping[str, object], part).get(key)
        if value is not None:
            return _parse_retry_after(value)
    return None


def _retry_after_seconds_from_headers(headers: object) -> float | None:
    if not isinstance(headers, Mapping):
        return None
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == "retry-after":
            return _parse_retry_after(value)
    return None


def _parse_retry_after(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(0.0, float(value))
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


def _retry_reason_from_exception(error: Exception, source: str) -> dict[str, object]:
    info = normalize_provider_error(error, source=source).info
    reason: dict[str, object] = {
        "reason": info.code.value if hasattr(info.code, "value") else str(info.code),
    }
    if info.status_code is not None:
        reason["statusCode"] = info.status_code
    return reason


def _retry_reason_from_part(
    part: RawPart,
    request: ResolvedRequest,
    model,
) -> dict[str, object]:
    try:
        info = provider_error_info_from_raw(
            cast(Mapping[str, object], part),
            source=request.api,
            provider=request.provider,
            model=getattr(model, "id", None),
        )
    except Exception:
        return {"reason": "provider"}
    reason: dict[str, object] = {
        "reason": info.code.value if hasattr(info.code, "value") else str(info.code),
    }
    if info.status_code is not None:
        reason["statusCode"] = info.status_code
    return reason


__all__ = ["RawPartSource", "start_provider_runtime"]
