from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTS_STORE = "supportsStore"
SUPPORTS_DEVELOPER_ROLE = "supportsDeveloperRole"
SUPPORTS_REASONING_EFFORT = "supportsReasoningEffort"
REASONING_EFFORT_MAP = "reasoningEffortMap"
SUPPORTS_USAGE_IN_STREAMING = "supportsUsageInStreaming"
SUPPORTS_STREAM_REASONING_DELTA = "supportsStreamReasoningDelta"
MAX_TOKENS_FIELD = "maxTokensField"
REQUIRES_TOOL_RESULT_NAME = "requiresToolResultName"
REQUIRES_ASSISTANT_AFTER_TOOL_RESULT = "requiresAssistantAfterToolResult"
REQUIRES_THINKING_AS_TEXT = "requiresThinkingAsText"
THINKING_FORMAT = "thinkingFormat"
SUPPORTS_STRICT_MODE = "supportsStrictMode"
REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES = (
    "requiresReasoningContentOnAssistantMessages"
)
PROVIDER_TRANSPORT = "providerTransport"
OPENROUTER_ROUTING = "openRouterRouting"
VERCEL_GATEWAY_ROUTING = "vercelGatewayRouting"
ZAI_TOOL_STREAM = "zaiToolStream"
CACHE_CONTROL_FORMAT = "cacheControlFormat"
SEND_SESSION_AFFINITY_HEADERS = "sendSessionAffinityHeaders"
SEND_SESSION_ID_HEADER = "sendSessionIdHeader"
SUPPORTS_LONG_CACHE_RETENTION = "supportsLongCacheRetention"
SUPPORTS_PROMPT_CACHE_KEY = "supportsPromptCacheKey"
SUPPORTS_EAGER_TOOL_INPUT_STREAMING = "supportsEagerToolInputStreaming"
SUPPORTS_CACHE_CONTROL_ON_TOOLS = "supportsCacheControlOnTools"
FINE_GRAINED_TOOLS = "fineGrainedTools"
INTERLEAVED_THINKING = "interleavedThinking"
SUPPORTS_JSON_SCHEMA_STRUCTURED_OUTPUT = "supportsJsonSchemaStructuredOutput"
CODEX_INCLUDE_CLIENT_REQUEST_ID = "codexIncludeClientRequestId"
CODEX_INCLUDE_CONVERSATION_ID = "codexIncludeConversationId"
CODEX_PROMPT_CACHE_RETENTION = "codexPromptCacheRetention"
CODEX_ORIGINATOR = "codexOriginator"
CODEX_USER_AGENT = "codexUserAgent"
UPSTREAM_MODEL_ID = "upstreamModelId"

PROTOCOL_COMPAT_STATUS_MAPPINGS: tuple[tuple[str, str | None, str], ...] = (
    (SUPPORTS_STORE, None, "store"),
    (SUPPORTS_DEVELOPER_ROLE, "roles", "developer"),
    (SUPPORTS_USAGE_IN_STREAMING, "streaming", "usage"),
    (SUPPORTS_STREAM_REASONING_DELTA, "streaming", "reasoningDelta"),
    (SUPPORTS_REASONING_EFFORT, "reasoning", "effort"),
    (INTERLEAVED_THINKING, "reasoning", "interleaved"),
    (SUPPORTS_STRICT_MODE, "tools", "strictSchema"),
    (SUPPORTS_EAGER_TOOL_INPUT_STREAMING, "tools", "eagerInputStream"),
    (FINE_GRAINED_TOOLS, "tools", "fineGrained"),
    (SUPPORTS_CACHE_CONTROL_ON_TOOLS, "cache", "onTools"),
    (SUPPORTS_LONG_CACHE_RETENTION, "cache", "longRetention"),
    (SUPPORTS_PROMPT_CACHE_KEY, "cache", "promptKey"),
    (SEND_SESSION_AFFINITY_HEADERS, "session", "affinityHeaders"),
    (SEND_SESSION_ID_HEADER, "session", "idHeader"),
)

DIALECT_COMPAT_BOOL_MAPPINGS: tuple[tuple[str, str, str], ...] = (
    (REQUIRES_TOOL_RESULT_NAME, "tools", "resultNameRequired"),
    (REQUIRES_ASSISTANT_AFTER_TOOL_RESULT, "tools", "assistantBridgeRequired"),
    (REQUIRES_THINKING_AS_TEXT, "reasoning", "thinkingAsText"),
    (
        REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES,
        "reasoning",
        "assistantContentRequired",
    ),
    (ZAI_TOOL_STREAM, "tools", "streamFlag"),
)

DIALECT_COMPAT_VALUE_MAPPINGS: tuple[tuple[str, str | None, str], ...] = (
    (MAX_TOKENS_FIELD, None, "maxOutputTokensField"),
    (THINKING_FORMAT, "reasoning", "wireFormat"),
    (CACHE_CONTROL_FORMAT, "cache", "controlFormat"),
)

COMPAT_DEFAULTS: dict[str, object] = {
    SUPPORTS_STORE: False,
    SUPPORTS_DEVELOPER_ROLE: True,
    SUPPORTS_REASONING_EFFORT: False,
    REASONING_EFFORT_MAP: {},
    SUPPORTS_USAGE_IN_STREAMING: True,
    SUPPORTS_STREAM_REASONING_DELTA: False,
    MAX_TOKENS_FIELD: "max_tokens",
    REQUIRES_TOOL_RESULT_NAME: False,
    REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
    REQUIRES_THINKING_AS_TEXT: False,
    REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES: False,
    THINKING_FORMAT: None,
    SUPPORTS_STRICT_MODE: False,
    ZAI_TOOL_STREAM: False,
    CACHE_CONTROL_FORMAT: None,
    SEND_SESSION_AFFINITY_HEADERS: False,
    SEND_SESSION_ID_HEADER: True,
    SUPPORTS_LONG_CACHE_RETENTION: True,
    SUPPORTS_PROMPT_CACHE_KEY: False,
    SUPPORTS_EAGER_TOOL_INPUT_STREAMING: True,
    SUPPORTS_CACHE_CONTROL_ON_TOOLS: True,
    FINE_GRAINED_TOOLS: False,
    CODEX_INCLUDE_CLIENT_REQUEST_ID: False,
    CODEX_INCLUDE_CONVERSATION_ID: False,
    CODEX_PROMPT_CACHE_RETENTION: None,
    CODEX_ORIGINATOR: None,
    CODEX_USER_AGENT: None,
}


def compat_with_defaults(values: Mapping[str, object] | None) -> dict[str, object]:
    merged = dict(COMPAT_DEFAULTS)
    if values is not None:
        merged.update(dict(values))
    return merged


def compat_bool(
    values: Mapping[str, object] | None,
    key: str,
    *,
    default: bool = False,
) -> bool:
    if values is not None and key in values:
        return bool(values[key])
    return bool(COMPAT_DEFAULTS.get(key, default))


def compat_str(
    values: Mapping[str, object] | None,
    key: str,
    *,
    default: str | None = None,
) -> str | None:
    value = None
    if values is not None and key in values:
        value = values[key]
    else:
        value = COMPAT_DEFAULTS.get(key, default)
    return value if isinstance(value, str) else default


def compat_dict(values: Mapping[str, object] | None, key: str) -> dict[str, object]:
    value: Any
    if values is not None and key in values:
        value = values[key]
    else:
        value = COMPAT_DEFAULTS.get(key, {})
    return dict(value) if isinstance(value, Mapping) else {}


STANDARD_COMPAT_PROFILES: dict[str, dict[str, object]] = {
    "openai-completions": {
        SUPPORTS_STORE: True,
        SUPPORTS_DEVELOPER_ROLE: True,
        SUPPORTS_REASONING_EFFORT: True,
        REASONING_EFFORT_MAP: {},
        SUPPORTS_USAGE_IN_STREAMING: True,
        SUPPORTS_STREAM_REASONING_DELTA: False,
        MAX_TOKENS_FIELD: "max_completion_tokens",
        REQUIRES_TOOL_RESULT_NAME: False,
        REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
        REQUIRES_THINKING_AS_TEXT: False,
        REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES: False,
        THINKING_FORMAT: "openai",
        ZAI_TOOL_STREAM: False,
        SUPPORTS_STRICT_MODE: True,
        CACHE_CONTROL_FORMAT: None,
        SEND_SESSION_AFFINITY_HEADERS: False,
        SUPPORTS_LONG_CACHE_RETENTION: True,
    },
    "openai-responses": {
        SUPPORTS_DEVELOPER_ROLE: True,
        REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
        SEND_SESSION_ID_HEADER: True,
        SUPPORTS_LONG_CACHE_RETENTION: True,
        SUPPORTS_PROMPT_CACHE_KEY: True,
    },
    "anthropic-messages": {
        SUPPORTS_EAGER_TOOL_INPUT_STREAMING: True,
        SUPPORTS_LONG_CACHE_RETENTION: True,
        SEND_SESSION_AFFINITY_HEADERS: False,
        SUPPORTS_CACHE_CONTROL_ON_TOOLS: True,
    },
}


def _standard_profile(name: str) -> dict[str, object]:
    return {
        key: dict(value) if isinstance(value, Mapping) else value
        for key, value in STANDARD_COMPAT_PROFILES[name].items()
    }


def _merge_profile_compat(
    overrides: Mapping[str, object],
    profile: Mapping[str, object],
    *,
    enabled_keys: tuple[str, ...] = (),
    bool_keys: tuple[str, ...] = (),
    value_keys: tuple[str, ...] = (),
    optional_value_keys: tuple[str, ...] = (),
) -> dict[str, object]:
    merged: dict[str, object] = {}
    for key in enabled_keys:
        merged[key] = _compat_override(overrides, profile, key) is not False
    for key in bool_keys:
        merged[key] = bool(_compat_override(overrides, profile, key))
    for key in value_keys:
        merged[key] = _compat_override(overrides, profile, key)
    for key in optional_value_keys:
        if key in overrides:
            merged[key] = overrides[key]
        elif key in profile:
            merged[key] = profile[key]
        elif key in COMPAT_DEFAULTS:
            value = COMPAT_DEFAULTS[key]
            if value is not None:
                merged[key] = value
    return merged


def _compat_override(
    overrides: Mapping[str, object],
    detected: Mapping[str, object],
    key: str,
) -> object:
    if key in overrides:
        return overrides[key]
    if key in detected:
        return detected[key]
    return COMPAT_DEFAULTS.get(key)


def resolve_openai_completions_compat(
    *,
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    compat = _merge_profile_compat(
        overrides,
        _standard_profile("openai-completions"),
        enabled_keys=(
            SUPPORTS_STORE,
            SUPPORTS_REASONING_EFFORT,
            SUPPORTS_USAGE_IN_STREAMING,
            SUPPORTS_STRICT_MODE,
            SUPPORTS_LONG_CACHE_RETENTION,
        ),
        bool_keys=(
            SUPPORTS_DEVELOPER_ROLE,
            REQUIRES_TOOL_RESULT_NAME,
            REQUIRES_ASSISTANT_AFTER_TOOL_RESULT,
            REQUIRES_THINKING_AS_TEXT,
            REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES,
            ZAI_TOOL_STREAM,
            SEND_SESSION_AFFINITY_HEADERS,
        ),
        value_keys=(
            REASONING_EFFORT_MAP,
            MAX_TOKENS_FIELD,
            THINKING_FORMAT,
            SUPPORTS_STREAM_REASONING_DELTA,
            CACHE_CONTROL_FORMAT,
        ),
        optional_value_keys=(
            OPENROUTER_ROUTING,
            VERCEL_GATEWAY_ROUTING,
        ),
    )
    if SUPPORTS_PROMPT_CACHE_KEY in overrides:
        compat[SUPPORTS_PROMPT_CACHE_KEY] = overrides[SUPPORTS_PROMPT_CACHE_KEY]
    return compat


def resolve_openai_responses_compat(
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    return _merge_profile_compat(
        overrides,
        _standard_profile("openai-responses"),
        enabled_keys=(
            SEND_SESSION_ID_HEADER,
            SUPPORTS_LONG_CACHE_RETENTION,
            SUPPORTS_PROMPT_CACHE_KEY,
        ),
        bool_keys=(
            SUPPORTS_DEVELOPER_ROLE,
            REQUIRES_ASSISTANT_AFTER_TOOL_RESULT,
        ),
    )


def resolve_anthropic_messages_compat(
    *,
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    compat = _merge_profile_compat(
        overrides,
        _standard_profile("anthropic-messages"),
        enabled_keys=(
            SUPPORTS_EAGER_TOOL_INPUT_STREAMING,
            SUPPORTS_LONG_CACHE_RETENTION,
            SUPPORTS_CACHE_CONTROL_ON_TOOLS,
        ),
        bool_keys=(SEND_SESSION_AFFINITY_HEADERS,),
        optional_value_keys=(INTERLEAVED_THINKING,),
    )
    if FINE_GRAINED_TOOLS in overrides:
        compat[FINE_GRAINED_TOOLS] = overrides[FINE_GRAINED_TOOLS]
    return compat
