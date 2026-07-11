from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from loushang.ai.auth.credentials import AuthCredential
from loushang.ai.structured import StructuredOutputOptions
from loushang.auth.types import OAuthCredentials

PairingMode = Literal["strict", "repair"]

ThinkingLevel = Literal["minimal", "low", "medium", "high", "xhigh"]


CacheRetention = Literal["none", "short", "long"]


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
    cancellation: object | None = None
    auth: AuthCredential | None = None
    api_key: str | None = field(default=None, repr=False)
    oauth_credentials: OAuthCredentials | None = field(default=None, repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    cache_retention: CacheRetention | None = None
    cache_key: str | None = None
    max_output_tokens: int | None = None
    temperature: float | int | None = None
    timeout: TimeoutOptions | None = None
    retry: RetryOptions | None = None
    trace: object | None = None
    pairing_mode: PairingMode = "strict"
    reasoning: ReasoningOptions | None = None
    tool_choice: ToolChoice | None = None
    output: StructuredOutputOptions | None = None

    def __post_init__(self) -> None:
        if self.auth is not None and (
            self.api_key is not None
            or self.oauth_credentials is not None
            or bool(self.headers)
        ):
            raise ValueError(
                "auth cannot be combined with api_key, oauth_credentials, or headers"
            )
        if self.api_key is not None:
            if not isinstance(self.api_key, str):
                raise TypeError("api_key must be a string or None")
            if not self.api_key.strip():
                raise ValueError("api_key must be non-empty")
            object.__setattr__(self, "api_key", self.api_key.strip())
        if self.oauth_credentials is not None:
            if not isinstance(self.oauth_credentials, OAuthCredentials):
                raise TypeError("oauth_credentials must be OAuthCredentials or None")
            if not isinstance(self.oauth_credentials.provider, str):
                raise TypeError("oauth_credentials.provider must be a string")
            if not self.oauth_credentials.provider.strip():
                raise ValueError("oauth_credentials.provider must be non-empty")
            if not isinstance(self.oauth_credentials.access_token, str):
                raise TypeError("oauth_credentials.access_token must be a string")
            if not self.oauth_credentials.access_token.strip():
                raise ValueError("oauth_credentials.access_token must be non-empty")
        if self.api_key is not None and self.oauth_credentials is not None:
            raise ValueError("api_key and oauth_credentials are mutually exclusive")
        normalized_headers = _validate_headers(self.headers, field_name="headers")
        object.__setattr__(self, "headers", normalized_headers)
        if self.cache_key is not None:
            if not isinstance(self.cache_key, str):
                raise TypeError("cache_key must be a string or None")
            if not self.cache_key.strip():
                raise ValueError("cache_key must be non-empty")
        if self.reasoning is not None and not isinstance(
            self.reasoning, ReasoningOptions
        ):
            raise TypeError("reasoning must be ReasoningOptions")


def _validate_headers(value: object, *, field_name: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping of strings")
    headers: dict[str, str] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not key:
            raise TypeError(f"{field_name} keys must be non-empty strings")
        if not isinstance(entry, str) or not entry:
            raise TypeError(f"{field_name} values must be non-empty strings")
        headers[key] = entry
    return headers


def get_max_output_tokens(options: object | None) -> int | None:
    if options is None:
        return None
    value = getattr(options, "max_output_tokens", None)
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
    return None


def get_reasoning_summary(options: object | None) -> str | None:
    if options is None:
        return None
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
    return None


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
    return False


def get_timeout_seconds(options: object | None) -> float | int | None:
    if options is None:
        return None
    timeout = getattr(options, "timeout", None)
    if isinstance(timeout, TimeoutOptions):
        value = timeout.total_seconds
        return value if isinstance(value, int | float) and value > 0 else None
    return None


def get_retry_attempts(options: object | None) -> int | None:
    if options is None:
        return None
    retry = getattr(options, "retry", None)
    if isinstance(retry, RetryOptions):
        return retry.max_attempts
    return None


def get_retry_max_delay_ms(options: object | None) -> int | None:
    if options is None:
        return None
    retry = getattr(options, "retry", None)
    if isinstance(retry, RetryOptions):
        return int(max(0.0, retry.max_delay_seconds) * 1000)
    return None


__all__ = [
    "CacheRetention",
    "CallOptions",
    "PairingMode",
    "ReasoningOptions",
    "RetryOptions",
    "StructuredOutputOptions",
    "ThinkingLevel",
    "TimeoutOptions",
    "ToolChoice",
]
