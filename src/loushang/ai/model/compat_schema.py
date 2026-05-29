from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTS_STORE = "supportsStore"
SUPPORTS_DEVELOPER_ROLE = "supportsDeveloperRole"
SUPPORTS_REASONING_EFFORT = "supportsReasoningEffort"
REASONING_EFFORT_MAP = "reasoningEffortMap"
SUPPORTS_USAGE_IN_STREAMING = "supportsUsageInStreaming"
MAX_TOKENS_FIELD = "maxTokensField"
REQUIRES_TOOL_RESULT_NAME = "requiresToolResultName"
REQUIRES_ASSISTANT_AFTER_TOOL_RESULT = "requiresAssistantAfterToolResult"
REQUIRES_THINKING_AS_TEXT = "requiresThinkingAsText"
THINKING_FORMAT = "thinkingFormat"
SUPPORTS_STRICT_MODE = "supportsStrictMode"
REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES = (
    "requiresReasoningContentOnAssistantMessages"
)
OPENROUTER_ROUTING = "openRouterRouting"
VERCEL_GATEWAY_ROUTING = "vercelGatewayRouting"
ZAI_TOOL_STREAM = "zaiToolStream"
CACHE_CONTROL_FORMAT = "cacheControlFormat"
SEND_SESSION_AFFINITY_HEADERS = "sendSessionAffinityHeaders"
SEND_SESSION_ID_HEADER = "sendSessionIdHeader"
SUPPORTS_LONG_CACHE_RETENTION = "supportsLongCacheRetention"
SUPPORTS_EAGER_TOOL_INPUT_STREAMING = "supportsEagerToolInputStreaming"
SUPPORTS_CACHE_CONTROL_ON_TOOLS = "supportsCacheControlOnTools"
CODEX_INCLUDE_CLIENT_REQUEST_ID = "codexIncludeClientRequestId"
CODEX_INCLUDE_CONVERSATION_ID = "codexIncludeConversationId"
CODEX_PROMPT_CACHE_RETENTION = "codexPromptCacheRetention"
CODEX_ORIGINATOR = "codexOriginator"
CODEX_USER_AGENT = "codexUserAgent"

COMPAT_DEFAULTS: dict[str, object] = {
    SUPPORTS_STORE: False,
    SUPPORTS_DEVELOPER_ROLE: True,
    SUPPORTS_REASONING_EFFORT: False,
    REASONING_EFFORT_MAP: {},
    SUPPORTS_USAGE_IN_STREAMING: True,
    MAX_TOKENS_FIELD: "max_tokens",
    REQUIRES_TOOL_RESULT_NAME: False,
    REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
    REQUIRES_THINKING_AS_TEXT: False,
    REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES: False,
    THINKING_FORMAT: None,
    SUPPORTS_STRICT_MODE: False,
    OPENROUTER_ROUTING: {},
    VERCEL_GATEWAY_ROUTING: {},
    ZAI_TOOL_STREAM: False,
    CACHE_CONTROL_FORMAT: None,
    SEND_SESSION_AFFINITY_HEADERS: False,
    SEND_SESSION_ID_HEADER: True,
    SUPPORTS_LONG_CACHE_RETENTION: True,
    SUPPORTS_EAGER_TOOL_INPUT_STREAMING: True,
    SUPPORTS_CACHE_CONTROL_ON_TOOLS: True,
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


def _merge_detected_compat(
    overrides: Mapping[str, object],
    detected: Mapping[str, object],
    *,
    enabled_keys: tuple[str, ...] = (),
    bool_keys: tuple[str, ...] = (),
    value_keys: tuple[str, ...] = (),
) -> dict[str, object]:
    merged: dict[str, object] = {}
    for key in enabled_keys:
        merged[key] = _compat_override(overrides, detected, key) is not False
    for key in bool_keys:
        merged[key] = bool(_compat_override(overrides, detected, key))
    for key in value_keys:
        merged[key] = _compat_override(overrides, detected, key)
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
    provider_id: str,
    model_id: str,
    base_url: str | None,
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    detected = _detect_openai_completions_compat(
        provider_id=provider_id,
        model_id=model_id,
        base_url=base_url,
    )
    overrides = dict(raw or {})
    return _merge_detected_compat(
        overrides,
        detected,
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
            OPENROUTER_ROUTING,
            VERCEL_GATEWAY_ROUTING,
            CACHE_CONTROL_FORMAT,
        ),
    )


def resolve_openai_responses_compat(
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    detected = {
        SUPPORTS_DEVELOPER_ROLE: True,
        REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
        SEND_SESSION_ID_HEADER: True,
        SUPPORTS_LONG_CACHE_RETENTION: True,
    }
    return _merge_detected_compat(
        overrides,
        detected,
        enabled_keys=(
            SEND_SESSION_ID_HEADER,
            SUPPORTS_LONG_CACHE_RETENTION,
        ),
        bool_keys=(
            SUPPORTS_DEVELOPER_ROLE,
            REQUIRES_ASSISTANT_AFTER_TOOL_RESULT,
        ),
    )


def resolve_anthropic_messages_compat(
    *,
    provider_id: str,
    base_url: str | None,
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    base_url = str(base_url or "")
    is_fireworks = provider_id == "fireworks"
    is_cloudflare_gateway = (
        provider_id == "cloudflare-ai-gateway" and "anthropic" in base_url
    )
    detected = {
        SUPPORTS_EAGER_TOOL_INPUT_STREAMING: not is_fireworks,
        SUPPORTS_LONG_CACHE_RETENTION: not is_fireworks,
        SEND_SESSION_AFFINITY_HEADERS: bool(is_fireworks or is_cloudflare_gateway),
        SUPPORTS_CACHE_CONTROL_ON_TOOLS: not is_fireworks,
    }
    overrides = dict(raw or {})
    return _merge_detected_compat(
        overrides,
        detected,
        enabled_keys=(
            SUPPORTS_EAGER_TOOL_INPUT_STREAMING,
            SUPPORTS_LONG_CACHE_RETENTION,
            SUPPORTS_CACHE_CONTROL_ON_TOOLS,
        ),
        bool_keys=(SEND_SESSION_AFFINITY_HEADERS,),
    )


def _detect_openai_completions_compat(
    *,
    provider_id: str,
    model_id: str,
    base_url: str | None,
) -> dict[str, object]:
    base_url = str(base_url or "")
    is_zai = provider_id == "zai" or "api.z.ai" in base_url
    is_together = (
        provider_id == "together"
        or "api.together.ai" in base_url
        or "api.together.xyz" in base_url
    )
    is_moonshot = (
        provider_id in {"moonshot", "moonshotai", "moonshotai-cn"}
        or "api.moonshot." in base_url
    )
    is_cloudflare_workers_ai = (
        provider_id == "cloudflare-workers-ai" or "api.cloudflare.com" in base_url
    )
    is_cloudflare_ai_gateway = (
        provider_id == "cloudflare-ai-gateway"
        or "gateway.ai.cloudflare.com" in base_url
    )
    is_qwen = (
        "dashscope.aliyuncs.com/compatible-mode" in base_url
        or "dashscope-intl.aliyuncs.com/compatible-mode" in base_url
        or "dashscope-us.aliyuncs.com/compatible-mode" in base_url
    )
    is_openrouter = provider_id == "openrouter" or "openrouter.ai" in base_url
    is_deepseek = provider_id == "deepseek" or "deepseek.com" in base_url
    is_grok = provider_id == "xai" or "api.x.ai" in base_url
    is_non_standard = (
        provider_id == "cerebras"
        or "cerebras.ai" in base_url
        or is_grok
        or is_together
        or "chutes.ai" in base_url
        or is_deepseek
        or is_zai
        or is_moonshot
        or provider_id == "opencode"
        or "opencode.ai" in base_url
        or is_cloudflare_workers_ai
        or is_cloudflare_ai_gateway
    )
    use_max_tokens = (
        "chutes.ai" in base_url
        or is_moonshot
        or is_cloudflare_ai_gateway
        or is_together
    )
    reasoning_effort_map = (
        {
            "minimal": "default",
            "low": "default",
            "medium": "default",
            "high": "default",
            "xhigh": "default",
        }
        if "groq.com" in base_url and model_id == "qwen/qwen3-32b"
        else {}
    )
    if is_deepseek:
        thinking_format = "deepseek"
    elif is_zai:
        thinking_format = "zai"
    elif is_qwen:
        thinking_format = "qwen"
    elif is_moonshot:
        thinking_format = "moonshot"
    elif is_together:
        thinking_format = "together"
    elif is_openrouter:
        thinking_format = "openrouter"
    else:
        thinking_format = "openai"

    return {
        SUPPORTS_STORE: not is_non_standard,
        SUPPORTS_DEVELOPER_ROLE: not is_non_standard,
        SUPPORTS_REASONING_EFFORT: not (
            is_grok or is_zai or is_qwen or is_moonshot or is_together
        ),
        REASONING_EFFORT_MAP: reasoning_effort_map,
        SUPPORTS_USAGE_IN_STREAMING: True,
        MAX_TOKENS_FIELD: "max_tokens" if use_max_tokens else "max_completion_tokens",
        REQUIRES_TOOL_RESULT_NAME: False,
        REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
        REQUIRES_THINKING_AS_TEXT: False,
        REQUIRES_REASONING_CONTENT_ON_ASSISTANT_MESSAGES: is_deepseek,
        THINKING_FORMAT: thinking_format,
        OPENROUTER_ROUTING: {},
        VERCEL_GATEWAY_ROUTING: {},
        ZAI_TOOL_STREAM: False,
        SUPPORTS_STRICT_MODE: not (
            is_moonshot or is_together or is_cloudflare_ai_gateway
        ),
        CACHE_CONTROL_FORMAT: "anthropic"
        if is_openrouter and model_id.startswith("anthropic/")
        else None,
        SEND_SESSION_AFFINITY_HEADERS: False,
        SUPPORTS_LONG_CACHE_RETENTION: not (
            is_together or is_cloudflare_workers_ai or is_cloudflare_ai_gateway
        ),
    }
