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
    },
    "azure-openai-responses": {
        SUPPORTS_DEVELOPER_ROLE: True,
        REQUIRES_ASSISTANT_AFTER_TOOL_RESULT: False,
        SEND_SESSION_ID_HEADER: False,
        SUPPORTS_LONG_CACHE_RETENTION: False,
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
    provider_id: str = "",
    model_id: str = "",
    base_url: str | None = None,
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    _require_explicit_openai_completions_contract(
        provider_id=provider_id,
        model_id=model_id,
        base_url=base_url,
        overrides=overrides,
    )
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
        ),
        bool_keys=(
            SUPPORTS_DEVELOPER_ROLE,
            REQUIRES_ASSISTANT_AFTER_TOOL_RESULT,
        ),
    )


def resolve_azure_openai_responses_compat(
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    compat = _merge_profile_compat(
        overrides,
        _standard_profile("azure-openai-responses"),
        bool_keys=(
            SUPPORTS_DEVELOPER_ROLE,
            REQUIRES_ASSISTANT_AFTER_TOOL_RESULT,
            SEND_SESSION_ID_HEADER,
            SUPPORTS_LONG_CACHE_RETENTION,
        ),
    )
    # The Azure adapter does not currently emit session headers or prompt-cache
    # retention fields, so those execution facts stay false even for legacy input.
    compat[SEND_SESSION_ID_HEADER] = False
    compat[SUPPORTS_LONG_CACHE_RETENTION] = False
    return compat


def resolve_anthropic_messages_compat(
    *,
    provider_id: str = "",
    base_url: str | None = None,
    raw: Mapping[str, object] | None = None,
) -> dict[str, object]:
    overrides = dict(raw or {})
    _require_explicit_anthropic_messages_contract(
        provider_id=provider_id,
        base_url=base_url,
        overrides=overrides,
    )
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


def _require_explicit_openai_completions_contract(
    *,
    provider_id: str,
    model_id: str,
    base_url: str | None,
    overrides: Mapping[str, object],
) -> None:
    legacy_contract = _legacy_openai_completions_contract(
        provider_id=provider_id,
        model_id=model_id,
        base_url=base_url,
    )
    _require_explicit_legacy_contract_keys(
        api="openai-completions",
        provider_id=provider_id,
        base_url=base_url,
        overrides=overrides,
        legacy_contract=legacy_contract,
        standard_contract=_standard_profile("openai-completions"),
    )


def _require_explicit_anthropic_messages_contract(
    *,
    provider_id: str,
    base_url: str | None,
    overrides: Mapping[str, object],
) -> None:
    legacy_contract = _legacy_anthropic_messages_contract(
        provider_id=provider_id,
        base_url=base_url,
    )
    _require_explicit_legacy_contract_keys(
        api="anthropic-messages",
        provider_id=provider_id,
        base_url=base_url,
        overrides=overrides,
        legacy_contract=legacy_contract,
        standard_contract=_standard_profile("anthropic-messages"),
    )


def _require_explicit_legacy_contract_keys(
    *,
    api: str,
    provider_id: str,
    base_url: str | None,
    overrides: Mapping[str, object],
    legacy_contract: Mapping[str, object],
    standard_contract: Mapping[str, object],
) -> None:
    missing = sorted(
        key
        for key, value in legacy_contract.items()
        if standard_contract.get(key, COMPAT_DEFAULTS.get(key)) != value
        and key not in overrides
    )
    if not missing:
        return
    identity = provider_id or str(base_url or "")
    raise ValueError(
        f"{api} endpoint {identity!r} matches a legacy non-standard adapter "
        "profile; declare explicit compat keys: "
        + ", ".join(missing)
    )


def _legacy_anthropic_messages_contract(
    *,
    provider_id: str,
    base_url: str | None,
) -> dict[str, object]:
    base_url_text = str(base_url or "")
    is_fireworks = provider_id == "fireworks" or "api.fireworks.ai" in base_url_text
    is_cloudflare_gateway = (
        provider_id == "cloudflare-ai-gateway" and "anthropic" in base_url_text
    )
    if not is_fireworks and not is_cloudflare_gateway:
        return {}
    return {
        SUPPORTS_EAGER_TOOL_INPUT_STREAMING: not is_fireworks,
        SUPPORTS_LONG_CACHE_RETENTION: not is_fireworks,
        SEND_SESSION_AFFINITY_HEADERS: bool(is_fireworks or is_cloudflare_gateway),
        SUPPORTS_CACHE_CONTROL_ON_TOOLS: not is_fireworks,
    }


def _legacy_openai_completions_contract(
    *,
    provider_id: str,
    model_id: str,
    base_url: str | None,
) -> dict[str, object]:
    base_url_text = str(base_url or "")
    is_zai = provider_id == "zai" or "api.z.ai" in base_url_text
    is_together = (
        provider_id == "together"
        or "api.together.ai" in base_url_text
        or "api.together.xyz" in base_url_text
    )
    is_moonshot = (
        provider_id in {"moonshot", "moonshotai", "moonshotai-cn"}
        or "api.moonshot." in base_url_text
    )
    is_cloudflare_workers_ai = (
        provider_id == "cloudflare-workers-ai" or "api.cloudflare.com" in base_url_text
    )
    is_cloudflare_ai_gateway = (
        provider_id == "cloudflare-ai-gateway"
        or "gateway.ai.cloudflare.com" in base_url_text
    )
    is_qwen = (
        "dashscope.aliyuncs.com/compatible-mode" in base_url_text
        or "dashscope-intl.aliyuncs.com/compatible-mode" in base_url_text
        or "dashscope-us.aliyuncs.com/compatible-mode" in base_url_text
    )
    is_openrouter = provider_id == "openrouter" or "openrouter.ai" in base_url_text
    is_deepseek = provider_id == "deepseek" or "deepseek.com" in base_url_text
    is_grok = provider_id == "xai" or "api.x.ai" in base_url_text
    is_non_standard = (
        provider_id == "cerebras"
        or "cerebras.ai" in base_url_text
        or is_grok
        or is_together
        or "chutes.ai" in base_url_text
        or is_deepseek
        or is_zai
        or is_moonshot
        or provider_id == "opencode"
        or "opencode.ai" in base_url_text
        or is_cloudflare_workers_ai
        or is_cloudflare_ai_gateway
    )
    use_max_tokens = (
        "chutes.ai" in base_url_text
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
        if "groq.com" in base_url_text and model_id == "qwen/qwen3-32b"
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
    if (
        not is_non_standard
        and not is_qwen
        and not is_openrouter
        and not reasoning_effort_map
    ):
        return {}
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
