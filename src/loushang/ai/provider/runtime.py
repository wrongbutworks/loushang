from __future__ import annotations

import asyncio
import inspect
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.options import RetryOptions
from loushang.ai.provider.cancellation import is_signal_cancelled
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
        signal = getattr(options, "signal", None) if options is not None else None
        if is_signal_cancelled(signal):
            assembler.feed({"type": "aborted"})
            return
        max_attempts = _retry_max_attempts(options)
        attempt = 1
        while attempt <= max_attempts:
            pending: list[RawPart] = []
            visible_output_started = False
            retry_next_attempt = False
            try:
                source = raw_parts()
                if inspect.isawaitable(source):
                    source = await source
                async for part in source:
                    if is_signal_cancelled(signal):
                        _flush_pending(assembler, pending)
                        assembler.feed({"type": "aborted"})
                        return

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
                        )
                        retry_next_attempt = True
                        break

                    if part["type"] in _VISIBLE_RAW_PART_TYPES:
                        _flush_pending(assembler, pending)
                        visible_output_started = True
                        assembler.feed(part)
                        continue

                    if visible_output_started or part["type"] in _TERMINAL_RAW_PART_TYPES:
                        _flush_pending(assembler, pending)
                        assembler.feed(part)
                        if part["type"] in _TERMINAL_RAW_PART_TYPES:
                            return
                        continue

                    pending.append(part)

                if retry_next_attempt:
                    attempt += 1
                    continue
                _flush_pending(assembler, pending)
                return
            except Exception as error:
                if is_signal_cancelled(signal):
                    _flush_pending(assembler, pending)
                    assembler.feed({"type": "aborted"})
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
                    )
                    attempt += 1
                    continue
                _flush_pending(assembler, pending)
                assembler.feed(
                    cast(RawPart, provider_error_part(error, source=request.api))
                )
                return

    stream.attach_task(asyncio.create_task(_run()))
    return stream


def _flush_pending(assembler: RawAssembler, pending: list[RawPart]) -> None:
    while pending:
        assembler.feed(pending.pop(0))


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
        await sleep(delay_seconds)


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
