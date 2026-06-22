from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypedDict

from loushang.ai.structured import StructuredOutputOptions

PairingMode = Literal["strict", "repair"]

ThinkingLevel = Literal["minimal", "low", "medium", "high", "xhigh"]


class ThinkingBudgets(TypedDict, total=False):
    minimal: int
    low: int
    medium: int
    high: int


CacheRetention = Literal["none", "short", "long"]


Transport = Literal["sse", "websocket", "auto"]


ToolChoice = str | dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReasoningOptions:
    enabled: bool | None = None
    effort: ThinkingLevel | str | None = None
    budget_tokens: int | None = None
    expose_summary: bool = False


@dataclass(frozen=True, slots=True)
class RetryOptions:
    max_attempts: int = 1
    max_delay_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class TimeoutOptions:
    connect_seconds: float | int | None = None
    total_seconds: float | int | None = None
    idle_seconds: float | int | None = None


@dataclass(frozen=True, slots=True)
class CallOptions:
    signal: object | None = None
    cancellation: object | None = None
    api_key: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    transport: Transport | None = None
    cache_retention: CacheRetention | None = None
    session_id: str | None = None
    max_retry_delay_ms: int | None = None
    metadata: Mapping[str, object] | None = None
    max_tokens: int | None = None
    max_output_tokens: int | None = None
    temperature: float | int | None = None
    timeout: TimeoutOptions | float | int | None = None
    retries: int | None = None
    retry: RetryOptions | None = None
    on_payload: object | None = None
    on_response: object | None = None
    trace: object | None = None
    oauth_credentials: dict[str, object] | None = None
    region: str | None = None
    pairing_mode: PairingMode = "strict"
    reasoning: ReasoningOptions | ThinkingLevel | str | None = None
    reasoning_summary: str | None = None
    tool_choice: ToolChoice | None = None
    output: StructuredOutputOptions | None = None
    hooks: object | None = None
    provider_options: Mapping[str, object] = field(default_factory=dict)


ModelCallOptions = CallOptions
StreamOptions = CallOptions
ProviderStreamOptions = CallOptions


def get_max_output_tokens(options: object | None) -> int | None:
    if options is None:
        return None
    value = getattr(options, "max_output_tokens", None)
    if isinstance(value, int):
        return value
    value = getattr(options, "max_tokens", None)
    return value if isinstance(value, int) else None


def get_reasoning_options(options: object | None) -> ReasoningOptions | None:
    if options is None:
        return None
    value = getattr(options, "reasoning", None)
    return value if isinstance(value, ReasoningOptions) else None


def get_reasoning_effort(options: object | None) -> str | None:
    if options is None:
        return None
    reasoning = getattr(options, "reasoning", None)
    if isinstance(reasoning, ReasoningOptions):
        return reasoning.effort if isinstance(reasoning.effort, str) else None
    if isinstance(reasoning, str):
        return reasoning
    for name in ("reasoning_effort", "reasoningEffort", "effort"):
        value = getattr(options, name, None)
        if isinstance(value, str):
            return value
    return None


def get_reasoning_summary(options: object | None) -> str | None:
    if options is None:
        return None
    value = getattr(options, "reasoning_summary", None) or getattr(
        options, "reasoningSummary", None
    )
    if isinstance(value, str):
        return value
    reasoning = get_reasoning_options(options)
    if reasoning is not None and reasoning.expose_summary:
        return "auto"
    return None


def get_reasoning_budget_tokens(options: object | None) -> int | None:
    if options is None:
        return None
    reasoning = get_reasoning_options(options)
    if reasoning is not None and isinstance(reasoning.budget_tokens, int):
        return reasoning.budget_tokens
    value = getattr(options, "thinking_budget_tokens", None)
    return value if isinstance(value, int) else None


def is_reasoning_requested(options: object | None) -> bool:
    if options is None:
        return False
    reasoning = get_reasoning_options(options)
    if reasoning is not None:
        return bool(
            reasoning.enabled
            or reasoning.effort
            or reasoning.budget_tokens
            or reasoning.expose_summary
        )
    if getattr(options, "emit_thinking", False):
        return True
    if getattr(options, "thinking_enabled", False):
        return True
    if get_reasoning_effort(options) is not None:
        return True
    if get_reasoning_summary(options) is not None:
        return True
    return get_reasoning_budget_tokens(options) is not None


def get_timeout_seconds(options: object | None) -> float | int | None:
    if options is None:
        return None
    timeout = getattr(options, "timeout", None)
    if isinstance(timeout, TimeoutOptions):
        value = timeout.total_seconds
        return value if isinstance(value, int | float) and value > 0 else None
    return timeout if isinstance(timeout, int | float) and timeout > 0 else None


def get_retry_attempts(options: object | None) -> int | None:
    if options is None:
        return None
    retry = getattr(options, "retry", None)
    if isinstance(retry, RetryOptions):
        return retry.max_attempts
    value = getattr(options, "retries", None)
    return value if isinstance(value, int) else None


def get_retry_max_delay_ms(options: object | None) -> int | None:
    if options is None:
        return None
    retry = getattr(options, "retry", None)
    if isinstance(retry, RetryOptions):
        return int(max(0.0, retry.max_delay_seconds) * 1000)
    value = getattr(options, "max_retry_delay_ms", None)
    return value if isinstance(value, int) else None


@dataclass(frozen=True, slots=True)
class SimpleCallOptions(CallOptions):
    reasoning: "ThinkingLevel | None" = None
    thinking_budgets: "ThinkingBudgets | None" = None


SimpleStreamOptions = SimpleCallOptions


def simple_options_to_call_options(
    options: SimpleCallOptions | None,
) -> CallOptions | None:
    if options is None:
        return None
    if not isinstance(options, SimpleCallOptions):
        raise TypeError("simple options must be SimpleCallOptions")
    budget_tokens = _simple_reasoning_budget_tokens(options)
    reasoning = (
        ReasoningOptions(
            enabled=True,
            effort=options.reasoning,
            budget_tokens=budget_tokens,
            expose_summary=True,
        )
        if options.reasoning is not None
        else None
    )
    return CallOptions(
        signal=options.signal,
        cancellation=options.cancellation,
        api_key=options.api_key,
        headers=options.headers,
        transport=options.transport,
        cache_retention=options.cache_retention,
        session_id=options.session_id,
        max_retry_delay_ms=options.max_retry_delay_ms,
        metadata=options.metadata,
        max_tokens=options.max_tokens,
        max_output_tokens=options.max_output_tokens,
        temperature=options.temperature,
        timeout=options.timeout,
        retries=options.retries,
        retry=options.retry,
        on_payload=options.on_payload,
        on_response=options.on_response,
        trace=options.trace,
        oauth_credentials=options.oauth_credentials,
        region=options.region,
        pairing_mode=options.pairing_mode,
        reasoning=reasoning,
        reasoning_summary=options.reasoning_summary,
        tool_choice=options.tool_choice,
        output=options.output,
        hooks=options.hooks,
        provider_options=options.provider_options,
    )


def _simple_reasoning_budget_tokens(options: SimpleCallOptions) -> int | None:
    if options.reasoning is None or options.thinking_budgets is None:
        return None
    value = options.thinking_budgets.get(options.reasoning)
    return value if isinstance(value, int) else None


from loushang.ai.advanced.options import (  # noqa: E402
    AnthropicOptions,
    OpenAICompletionsOptions,
    OpenAIResponsesOptions,
)

__all__ = [
    "AnthropicOptions",
    "CacheRetention",
    "CallOptions",
    "ModelCallOptions",
    "OpenAICompletionsOptions",
    "OpenAIResponsesOptions",
    "PairingMode",
    "ProviderStreamOptions",
    "ReasoningOptions",
    "RetryOptions",
    "SimpleCallOptions",
    "SimpleStreamOptions",
    "StreamOptions",
    "StructuredOutputOptions",
    "ThinkingBudgets",
    "ThinkingLevel",
    "TimeoutOptions",
    "ToolChoice",
    "Transport",
    "simple_options_to_call_options",
]
