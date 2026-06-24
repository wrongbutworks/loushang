from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import InitVar, dataclass, field
from math import isfinite
from typing import Literal, TypeAlias, cast

Modality = Literal["text", "image"]
ALLOWED_MODALITIES: tuple[Modality, ...] = ("text", "image")


def _normalize_optional_bool_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"adapter config field must be a boolean: {attr}")


def _normalize_optional_str_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"adapter config field must be a non-empty string: {attr}")


def _normalize_optional_transport_str_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"transport field must be a non-empty string: {attr}")


def _normalize_optional_transport_bool_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"transport field must be a boolean: {attr}")


def _normalize_optional_transport_number_attrs(instance: object, *attrs: str) -> None:
    for attr in attrs:
        value = getattr(instance, attr)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"transport field must be a positive number: {attr}")


def _optional_bool_from_raw(raw: Mapping[str, object], key: str) -> bool | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool):
        return value
    raise ValueError(f"adapter config field must be a boolean: {key}")


def _bool_from_raw(raw: Mapping[str, object], key: str, default: bool) -> bool:
    value = _optional_bool_from_raw(raw, key)
    return default if value is None else value


def _optional_str_from_raw(raw: Mapping[str, object], key: str) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"adapter config field must be a non-empty string: {key}")


def _optional_transport_str_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> str | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"transport field must be a non-empty string: {key}")


def _optional_transport_bool_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> bool | None:
    if key not in raw:
        return None
    value = raw[key]
    if isinstance(value, bool):
        return value
    raise ValueError(f"transport field must be a boolean: {key}")


def _optional_transport_number_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> float | int | None:
    if key not in raw:
        return None
    value = raw[key]
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"transport field must be a positive number: {key}")
    return value


def _copy_raw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _copy_raw_value(entry) for key, entry in value.items()}
    if isinstance(value, list):
        return [_copy_raw_value(entry) for entry in value]
    return value


def _copy_raw_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {key: _copy_raw_value(entry) for key, entry in value.items()}


def _deep_merge_raw_mapping(
    base: Mapping[str, object],
    override: Mapping[str, object],
) -> dict[str, object]:
    result = _copy_raw_mapping(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge_raw_mapping(existing, value)
            continue
        result[key] = _copy_raw_value(value)
    return result


def _routing_request_overrides_from_raw(
    raw: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    if "requestOverrides" not in raw:
        return {}
    value = raw["requestOverrides"]
    if not isinstance(value, Mapping):
        raise ValueError("routing field must be an object: requestOverrides")
    overrides: dict[str, dict[str, object]] = {}
    for key, entry in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("routing requestOverrides keys must be non-empty strings")
        if not isinstance(entry, Mapping):
            raise ValueError(
                "routing requestOverrides entries must be objects: "
                f"requestOverrides.{key}"
            )
        overrides[key] = _copy_raw_mapping(entry)
    return overrides


_EXTRA_BODY_RESERVED_KEYS = frozenset(
    {
        "model",
        "messages",
        "input",
        "stream",
        "tools",
        "tool_choice",
        "response_format",
        "max_tokens",
        "max_completion_tokens",
        "max_output_tokens",
        "temperature",
        "reasoning",
        "store",
        "stream_options",
        "extra_body",
        "parallel_tool_calls",
        "thinking",
    }
)

OPENAI_COMPLETIONS_ADAPTER_KEYS = frozenset(
    {
        "store",
        "developerRole",
        "streamingUsage",
        "maxOutputTokensField",
        "reasoningEffort",
        "reasoningEffortMap",
        "strictSchema",
        "promptCacheKey",
        "longCacheRetention",
        "sessionAffinityHeaders",
        "toolResultName",
        "assistantAfterToolResult",
        "thinkingAsText",
        "assistantReasoningContent",
        "toolStream",
        "reasoningFormat",
        "cacheControlFormat",
        "extraBody",
    }
)
OPENAI_RESPONSES_ADAPTER_KEYS = frozenset(
    {
        "developerRole",
        "assistantAfterToolResult",
        "promptCacheKey",
        "longCacheRetention",
        "sessionIdHeader",
        "sessionAffinityHeaders",
    }
)
ANTHROPIC_MESSAGES_ADAPTER_KEYS = frozenset(
    {
        "fineGrainedTools",
        "interleavedThinking",
        "sessionAffinityHeaders",
        "longCacheRetention",
    }
)


def _json_safe_copy(value: object, path: str) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, float) and not isfinite(value):
            raise ValueError(f"adapter extraBody value must be JSON-safe: {path}")
        return value
    if isinstance(value, list):
        return [_json_safe_copy(entry, f"{path}[]") for entry in value]
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, entry in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"adapter extraBody keys must be strings: {path}")
            result[key] = _json_safe_copy(entry, f"{path}.{key}")
        return result
    raise ValueError(f"adapter extraBody value must be JSON-safe: {path}")


def _extra_body_from_raw(raw: Mapping[str, object], key: str) -> dict[str, object]:
    if key not in raw:
        return {}
    value = raw[key]
    if not isinstance(value, Mapping):
        raise ValueError(f"adapter config field must be an object: {key}")
    result: dict[str, object] = {}
    for entry_key, entry_value in value.items():
        if not isinstance(entry_key, str) or not entry_key:
            raise ValueError(f"adapter extraBody keys must be strings: {key}")
        if entry_key in _EXTRA_BODY_RESERVED_KEYS:
            raise ValueError(
                f"adapter extraBody cannot override SDK field: {entry_key}"
            )
        result[entry_key] = _json_safe_copy(entry_value, f"{key}.{entry_key}")
    return result


def _string_or_none_dict_from_raw(
    raw: Mapping[str, object],
    key: str,
) -> dict[str, str | None]:
    if key not in raw:
        return {}
    value = raw[key]
    if not isinstance(value, Mapping):
        raise ValueError(f"adapter config field must be a string-or-null map: {key}")
    result: dict[str, str | None] = {}
    for entry_key, entry_value in value.items():
        if not isinstance(entry_key, str) or not (
            entry_value is None or isinstance(entry_value, str)
        ):
            raise ValueError(
                f"adapter config field must be a string-or-null map: {key}"
            )
        result[entry_key] = entry_value
    return result


def _with_raw_value(raw: dict[str, object], key: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, dict) and not value:
        return
    raw[key] = value


def _validate_adapter_keys(
    raw: Mapping[str, object],
    allowed_keys: frozenset[str],
) -> None:
    unknown = sorted(set(raw) - allowed_keys)
    if unknown:
        raise ValueError(f"adapter config has unknown keys: {unknown}")


def _set_explicit_adapter_keys(
    instance: object,
    *,
    attr_to_key: Mapping[str, str],
    defaults: Mapping[str, object],
    allowed_keys: frozenset[str],
) -> None:
    explicit_keys = getattr(instance, "_explicit_keys", None)
    if explicit_keys is None:
        explicit_keys = frozenset(
            key
            for attr, key in attr_to_key.items()
            if getattr(instance, attr) != defaults[key]
        )
    else:
        explicit_keys = frozenset(explicit_keys)
        unknown = sorted(set(explicit_keys) - allowed_keys)
        if unknown:
            raise ValueError(f"adapter config has unknown explicit keys: {unknown}")
    object.__setattr__(instance, "_explicit_keys", explicit_keys)


def _adapter_override_raw(config: AdapterConfig) -> dict[str, object]:
    explicit_keys = getattr(config, "_explicit_keys", None)
    if not explicit_keys:
        return {}
    raw = config.to_raw()
    return {key: raw[key] for key in explicit_keys if key in raw}


_OPENAI_COMPLETIONS_ATTR_TO_KEY = {
    "store": "store",
    "developer_role": "developerRole",
    "streaming_usage": "streamingUsage",
    "max_output_tokens_field": "maxOutputTokensField",
    "reasoning_effort": "reasoningEffort",
    "reasoning_effort_map": "reasoningEffortMap",
    "strict_schema": "strictSchema",
    "prompt_cache_key": "promptCacheKey",
    "long_cache_retention": "longCacheRetention",
    "session_affinity_headers": "sessionAffinityHeaders",
    "tool_result_name": "toolResultName",
    "assistant_after_tool_result": "assistantAfterToolResult",
    "thinking_as_text": "thinkingAsText",
    "assistant_reasoning_content": "assistantReasoningContent",
    "tool_stream": "toolStream",
    "reasoning_format": "reasoningFormat",
    "cache_control_format": "cacheControlFormat",
    "extra_body": "extraBody",
}
_OPENAI_COMPLETIONS_DEFAULTS = {
    "store": True,
    "developerRole": True,
    "streamingUsage": True,
    "maxOutputTokensField": "max_completion_tokens",
    "reasoningEffort": True,
    "reasoningEffortMap": {},
    "strictSchema": True,
    "promptCacheKey": False,
    "longCacheRetention": True,
    "sessionAffinityHeaders": False,
    "toolResultName": False,
    "assistantAfterToolResult": False,
    "thinkingAsText": False,
    "assistantReasoningContent": False,
    "toolStream": False,
    "reasoningFormat": "openai",
    "cacheControlFormat": None,
    "extraBody": {},
}


_OPENAI_RESPONSES_ATTR_TO_KEY = {
    "developer_role": "developerRole",
    "assistant_after_tool_result": "assistantAfterToolResult",
    "prompt_cache_key": "promptCacheKey",
    "long_cache_retention": "longCacheRetention",
    "session_id_header": "sessionIdHeader",
    "session_affinity_headers": "sessionAffinityHeaders",
}
_OPENAI_RESPONSES_DEFAULTS = {
    "developerRole": True,
    "assistantAfterToolResult": False,
    "promptCacheKey": True,
    "longCacheRetention": True,
    "sessionIdHeader": True,
    "sessionAffinityHeaders": False,
}


_ANTHROPIC_MESSAGES_ATTR_TO_KEY = {
    "fine_grained_tools": "fineGrainedTools",
    "interleaved_thinking": "interleavedThinking",
    "session_affinity_headers": "sessionAffinityHeaders",
    "long_cache_retention": "longCacheRetention",
}
_ANTHROPIC_MESSAGES_DEFAULTS = {
    "fineGrainedTools": None,
    "interleavedThinking": None,
    "sessionAffinityHeaders": False,
    "longCacheRetention": True,
}


@dataclass(frozen=True)
class OpenAICompletionsConfig:
    store: bool = True
    developer_role: bool = True
    streaming_usage: bool = True
    max_output_tokens_field: str = "max_completion_tokens"
    reasoning_effort: bool = True
    reasoning_effort_map: dict[str, str | None] = field(default_factory=dict)
    strict_schema: bool = True
    prompt_cache_key: bool = False
    long_cache_retention: bool = True
    session_affinity_headers: bool = False
    tool_result_name: bool = False
    assistant_after_tool_result: bool = False
    thinking_as_text: bool = False
    assistant_reasoning_content: bool = False
    tool_stream: bool = False
    reasoning_format: str | None = "openai"
    cache_control_format: str | None = None
    extra_body: dict[str, object] = field(default_factory=dict)
    _explicit_keys: frozenset[str] | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        _normalize_optional_bool_attrs(
            self,
            "store",
            "developer_role",
            "streaming_usage",
            "reasoning_effort",
            "strict_schema",
            "prompt_cache_key",
            "long_cache_retention",
            "session_affinity_headers",
            "tool_result_name",
            "assistant_after_tool_result",
            "thinking_as_text",
            "assistant_reasoning_content",
            "tool_stream",
        )
        _normalize_optional_str_attrs(
            self,
            "max_output_tokens_field",
            "reasoning_format",
            "cache_control_format",
        )
        object.__setattr__(
            self, "reasoning_effort_map", dict(self.reasoning_effort_map)
        )
        object.__setattr__(
            self,
            "extra_body",
            _extra_body_from_raw({"extraBody": self.extra_body}, "extraBody"),
        )
        _set_explicit_adapter_keys(
            self,
            attr_to_key=_OPENAI_COMPLETIONS_ATTR_TO_KEY,
            defaults=_OPENAI_COMPLETIONS_DEFAULTS,
            allowed_keys=OPENAI_COMPLETIONS_ADAPTER_KEYS,
        )

    @classmethod
    def from_raw(
        cls,
        raw: Mapping[str, object] | None,
    ) -> "OpenAICompletionsConfig":
        raw = raw or {}
        _validate_adapter_keys(raw, OPENAI_COMPLETIONS_ADAPTER_KEYS)
        return cls(
            store=_bool_from_raw(raw, "store", cls.store),
            developer_role=_bool_from_raw(raw, "developerRole", cls.developer_role),
            streaming_usage=_bool_from_raw(raw, "streamingUsage", cls.streaming_usage),
            max_output_tokens_field=_optional_str_from_raw(
                raw,
                "maxOutputTokensField",
            )
            or cls.max_output_tokens_field,
            reasoning_effort=_bool_from_raw(
                raw,
                "reasoningEffort",
                cls.reasoning_effort,
            ),
            reasoning_effort_map=_string_or_none_dict_from_raw(
                raw,
                "reasoningEffortMap",
            ),
            strict_schema=_bool_from_raw(raw, "strictSchema", cls.strict_schema),
            prompt_cache_key=_bool_from_raw(
                raw,
                "promptCacheKey",
                cls.prompt_cache_key,
            ),
            long_cache_retention=_bool_from_raw(
                raw,
                "longCacheRetention",
                cls.long_cache_retention,
            ),
            session_affinity_headers=_bool_from_raw(
                raw,
                "sessionAffinityHeaders",
                cls.session_affinity_headers,
            ),
            tool_result_name=_bool_from_raw(
                raw,
                "toolResultName",
                cls.tool_result_name,
            ),
            assistant_after_tool_result=_bool_from_raw(
                raw,
                "assistantAfterToolResult",
                cls.assistant_after_tool_result,
            ),
            thinking_as_text=_bool_from_raw(
                raw,
                "thinkingAsText",
                cls.thinking_as_text,
            ),
            assistant_reasoning_content=_bool_from_raw(
                raw,
                "assistantReasoningContent",
                cls.assistant_reasoning_content,
            ),
            tool_stream=_bool_from_raw(raw, "toolStream", cls.tool_stream),
            reasoning_format=_optional_str_from_raw(raw, "reasoningFormat")
            if "reasoningFormat" in raw
            else cls.reasoning_format,
            cache_control_format=_optional_str_from_raw(raw, "cacheControlFormat")
            if "cacheControlFormat" in raw
            else cls.cache_control_format,
            extra_body=_extra_body_from_raw(raw, "extraBody"),
            _explicit_keys=frozenset(raw),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "store": self.store,
            "developerRole": self.developer_role,
            "streamingUsage": self.streaming_usage,
            "maxOutputTokensField": self.max_output_tokens_field,
            "reasoningEffort": self.reasoning_effort,
            "strictSchema": self.strict_schema,
            "promptCacheKey": self.prompt_cache_key,
            "longCacheRetention": self.long_cache_retention,
            "sessionAffinityHeaders": self.session_affinity_headers,
            "toolResultName": self.tool_result_name,
            "assistantAfterToolResult": self.assistant_after_tool_result,
            "thinkingAsText": self.thinking_as_text,
            "assistantReasoningContent": self.assistant_reasoning_content,
            "toolStream": self.tool_stream,
        }
        _with_raw_value(raw, "reasoningEffortMap", dict(self.reasoning_effort_map))
        _with_raw_value(raw, "reasoningFormat", self.reasoning_format)
        _with_raw_value(raw, "cacheControlFormat", self.cache_control_format)
        _with_raw_value(raw, "extraBody", _copy_raw_mapping(self.extra_body))
        return raw


@dataclass(frozen=True)
class OpenAIResponsesConfig:
    developer_role: bool = True
    assistant_after_tool_result: bool = False
    prompt_cache_key: bool = True
    long_cache_retention: bool = True
    session_id_header: bool = True
    session_affinity_headers: bool = False
    _explicit_keys: frozenset[str] | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        _normalize_optional_bool_attrs(
            self,
            "developer_role",
            "assistant_after_tool_result",
            "prompt_cache_key",
            "long_cache_retention",
            "session_id_header",
            "session_affinity_headers",
        )
        _set_explicit_adapter_keys(
            self,
            attr_to_key=_OPENAI_RESPONSES_ATTR_TO_KEY,
            defaults=_OPENAI_RESPONSES_DEFAULTS,
            allowed_keys=OPENAI_RESPONSES_ADAPTER_KEYS,
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "OpenAIResponsesConfig":
        raw = raw or {}
        _validate_adapter_keys(raw, OPENAI_RESPONSES_ADAPTER_KEYS)
        return cls(
            developer_role=_bool_from_raw(raw, "developerRole", cls.developer_role),
            assistant_after_tool_result=_bool_from_raw(
                raw,
                "assistantAfterToolResult",
                cls.assistant_after_tool_result,
            ),
            prompt_cache_key=_bool_from_raw(
                raw,
                "promptCacheKey",
                cls.prompt_cache_key,
            ),
            long_cache_retention=_bool_from_raw(
                raw,
                "longCacheRetention",
                cls.long_cache_retention,
            ),
            session_id_header=_bool_from_raw(
                raw,
                "sessionIdHeader",
                cls.session_id_header,
            ),
            session_affinity_headers=_bool_from_raw(
                raw,
                "sessionAffinityHeaders",
                cls.session_affinity_headers,
            ),
            _explicit_keys=frozenset(raw),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "developerRole": self.developer_role,
            "assistantAfterToolResult": self.assistant_after_tool_result,
            "promptCacheKey": self.prompt_cache_key,
            "longCacheRetention": self.long_cache_retention,
            "sessionIdHeader": self.session_id_header,
            "sessionAffinityHeaders": self.session_affinity_headers,
        }


@dataclass(frozen=True)
class AnthropicMessagesConfig:
    fine_grained_tools: bool | None = None
    interleaved_thinking: bool | None = None
    session_affinity_headers: bool = False
    long_cache_retention: bool = True
    _explicit_keys: frozenset[str] | None = field(
        default=None,
        compare=False,
        repr=False,
        kw_only=True,
    )

    def __post_init__(self) -> None:
        _normalize_optional_bool_attrs(
            self,
            "fine_grained_tools",
            "interleaved_thinking",
            "session_affinity_headers",
            "long_cache_retention",
        )
        _set_explicit_adapter_keys(
            self,
            attr_to_key=_ANTHROPIC_MESSAGES_ATTR_TO_KEY,
            defaults=_ANTHROPIC_MESSAGES_DEFAULTS,
            allowed_keys=ANTHROPIC_MESSAGES_ADAPTER_KEYS,
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "AnthropicMessagesConfig":
        raw = raw or {}
        _validate_adapter_keys(raw, ANTHROPIC_MESSAGES_ADAPTER_KEYS)
        return cls(
            fine_grained_tools=_optional_bool_from_raw(raw, "fineGrainedTools")
            if "fineGrainedTools" in raw
            else cls.fine_grained_tools,
            interleaved_thinking=_optional_bool_from_raw(raw, "interleavedThinking")
            if "interleavedThinking" in raw
            else cls.interleaved_thinking,
            session_affinity_headers=_bool_from_raw(
                raw,
                "sessionAffinityHeaders",
                cls.session_affinity_headers,
            ),
            long_cache_retention=_bool_from_raw(
                raw,
                "longCacheRetention",
                cls.long_cache_retention,
            ),
            _explicit_keys=frozenset(raw),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "sessionAffinityHeaders": self.session_affinity_headers,
            "longCacheRetention": self.long_cache_retention,
        }
        _with_raw_value(raw, "fineGrainedTools", self.fine_grained_tools)
        _with_raw_value(raw, "interleavedThinking", self.interleaved_thinking)
        return raw


AdapterConfig: TypeAlias = (
    OpenAICompletionsConfig | OpenAIResponsesConfig | AnthropicMessagesConfig
)


def default_adapter_config(api: str) -> AdapterConfig | None:
    if api == "openai-completions":
        return OpenAICompletionsConfig()
    if api == "openai-responses":
        return OpenAIResponsesConfig()
    if api == "anthropic-messages":
        return AnthropicMessagesConfig()
    return None


def adapter_config_from_raw(
    api: str,
    raw: Mapping[str, object] | None,
) -> AdapterConfig | None:
    if api == "openai-completions":
        return OpenAICompletionsConfig.from_raw(raw)
    if api == "openai-responses":
        return OpenAIResponsesConfig.from_raw(raw)
    if api == "anthropic-messages":
        return AnthropicMessagesConfig.from_raw(raw)
    return None


def adapter_config_allowed_keys(api: str) -> frozenset[str]:
    if api == "openai-completions":
        return OPENAI_COMPLETIONS_ADAPTER_KEYS
    if api == "openai-responses":
        return OPENAI_RESPONSES_ADAPTER_KEYS
    if api == "anthropic-messages":
        return ANTHROPIC_MESSAGES_ADAPTER_KEYS
    return frozenset()


def merge_adapter_config(
    base: AdapterConfig | None,
    override: AdapterConfig | None,
) -> AdapterConfig | None:
    if override is None:
        return base
    if base is None:
        return override
    if type(base) is not type(override):
        raise ValueError("model adapter config must match endpoint adapter type")
    override_raw = _adapter_override_raw(override)
    if not override_raw:
        return base
    return type(base).from_raw({**base.to_raw(), **override_raw})


@dataclass(frozen=True)
class EndpointTransport:
    kind: str | None = None
    stream: str | None = None
    fallback: bool | None = None
    timeout: float | int | None = None

    def __post_init__(self) -> None:
        _normalize_optional_transport_str_attrs(self, "kind", "stream")
        _normalize_optional_transport_bool_attrs(self, "fallback")
        _normalize_optional_transport_number_attrs(self, "timeout")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointTransport":
        raw = raw or {}
        return cls(
            kind=_optional_transport_str_from_raw(raw, "kind"),
            stream=_optional_transport_str_from_raw(raw, "stream"),
            fallback=_optional_transport_bool_from_raw(raw, "fallback"),
            timeout=_optional_transport_number_from_raw(raw, "timeout"),
        )

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {}
        if self.kind is not None:
            raw["kind"] = self.kind
        if self.stream is not None:
            raw["stream"] = self.stream
        if self.fallback is not None:
            raw["fallback"] = self.fallback
        if self.timeout is not None:
            raw["timeout"] = self.timeout
        return raw


@dataclass(frozen=True)
class EndpointRouting:
    request_overrides: dict[str, dict[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key, value in self.request_overrides.items():
            if not isinstance(key, str) or not key:
                raise ValueError(
                    "routing requestOverrides keys must be non-empty strings"
                )
            if not isinstance(value, Mapping):
                raise ValueError(
                    "routing requestOverrides entries must be objects: "
                    f"requestOverrides.{key}"
                )
        object.__setattr__(
            self,
            "request_overrides",
            {
                key: _copy_raw_mapping(value)
                for key, value in self.request_overrides.items()
            },
        )

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "EndpointRouting":
        raw = raw or {}
        return cls(request_overrides=_routing_request_overrides_from_raw(raw))

    def to_raw(self) -> dict[str, object]:
        if not self.request_overrides:
            return {}
        return {
            "requestOverrides": {
                key: _copy_raw_mapping(value)
                for key, value in self.request_overrides.items()
            }
        }


@dataclass(frozen=True)
class Auth:
    kind: str = "apiKey"
    api_key_env: str | None = None
    api_key_envs: tuple[str, ...] = ()
    header: str = "Authorization"
    prefix: str = "Bearer "
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Auth | None":
        if not raw:
            return None
        return cls(
            kind=str(raw.get("kind", "apiKey")),
            api_key_env=_as_optional_str(raw.get("apiKeyEnv")),
            api_key_envs=_as_str_tuple(raw.get("apiKeyEnvs")),
            header=str(raw.get("header", "Authorization")),
            prefix=str(raw.get("prefix", "Bearer ")),
            extra_headers=_as_str_dict(raw.get("extraHeaders")),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "apiKeyEnv": self.api_key_env,
            "apiKeyEnvs": list(self.api_key_envs),
            "header": self.header,
            "prefix": self.prefix,
            "extraHeaders": dict(self.extra_headers),
        }


@dataclass(frozen=True)
class Pricing:
    currency: str | None = None
    input: float | int | None = None
    output: float | int | None = None
    cache_read: float | int | None = None
    cache_write: float | int | None = None

    def __post_init__(self) -> None:
        for attr in ("input", "output", "cache_read", "cache_write"):
            value = getattr(self, attr)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"pricing field must be a non-negative number: {attr}")

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Pricing | None":
        if raw is None:
            return None
        return cls(
            currency=_as_optional_str(raw.get("currency")),
            input=_as_optional_number(raw.get("input")),
            output=_as_optional_number(raw.get("output")),
            cache_read=_as_optional_number(raw.get("cacheRead")),
            cache_write=_as_optional_number(raw.get("cacheWrite")),
        )

    def to_raw(self) -> dict[str, object]:
        raw = {
            "currency": self.currency,
            "input": self.input,
            "output": self.output,
            "cacheRead": self.cache_read,
            "cacheWrite": self.cache_write,
        }
        return {key: value for key, value in raw.items() if value is not None}


@dataclass(frozen=True)
class Capabilities:
    input: tuple[Modality, ...] = ("text",)
    output: tuple[Modality, ...] = ("text",)
    context_window: int | None = None
    max_tokens: int | None = None
    reasoning: bool = False
    stream: bool = False
    tool_use: bool = False
    structured_output: bool = False
    attachment: bool = False
    temperature: bool = False

    @property
    def supports_thinking(self) -> bool:
        return self.reasoning

    @property
    def supports_image_input(self) -> bool:
        return "image" in self.input

    @property
    def supports_image_output(self) -> bool:
        return "image" in self.output

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Capabilities":
        raw = raw or {}
        capabilities_raw = raw.get("capabilities")
        if isinstance(capabilities_raw, Mapping):
            raw = capabilities_raw
        return cls(
            input=_parse_modalities(raw.get("input")),
            output=_parse_modalities(raw.get("output")),
            context_window=_as_optional_int(raw.get("contextWindow")),
            max_tokens=_as_optional_int(raw.get("maxTokens")),
            reasoning=bool(raw.get("reasoning", False)),
            stream=bool(raw.get("stream", False)),
            tool_use=bool(raw.get("toolUse", False)),
            structured_output=bool(raw.get("structuredOutput", False)),
            attachment=bool(raw.get("attachment", False)),
            temperature=bool(raw.get("temperature", False)),
        )

    def to_raw(self) -> dict[str, object]:
        return {
            "capabilities": {
                "contextWindow": self.context_window,
                "maxTokens": self.max_tokens,
                "input": list(self.input),
                "output": list(self.output),
                "reasoning": self.reasoning,
                "stream": self.stream,
                "toolUse": self.tool_use,
                "structuredOutput": self.structured_output,
                "attachment": self.attachment,
                "temperature": self.temperature,
            }
        }


@dataclass(frozen=True)
class Defaults(Mapping[str, object]):
    items_by_key: dict[str, object] = field(default_factory=dict)

    def __getitem__(self, key: str) -> object:
        return self.items_by_key[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.items_by_key)

    def __len__(self) -> int:
        return len(self.items_by_key)

    def get(self, key: str, default: object | None = None) -> object | None:
        return self.items_by_key.get(key, default)

    def merged(self, other: Mapping[str, object] | None = None) -> "Defaults":
        merged = dict(self.items_by_key)
        if other is not None:
            merged.update(dict(other))
        return Defaults(items_by_key=merged)

    @classmethod
    def from_raw(cls, raw: Mapping[str, object] | None) -> "Defaults":
        return cls(items_by_key=dict(raw or {}))

    def to_raw(self) -> dict[str, object]:
        return dict(self.items_by_key)


@dataclass(frozen=True)
class Model:
    id: str
    _endpoint_key: str = ""
    provider: InitVar[str | None] = None
    endpoint: InitVar[str | None] = None
    api: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    region: str | None = None
    lane: str | None = None
    preferred_endpoint: bool = False
    auth: Auth | None = None
    name: str | None = None
    family: str | None = None
    alias: str | None = None
    knowledge: str | None = None
    release_date: str | None = None
    last_updated: str | None = None
    capabilities: Capabilities = field(default_factory=Capabilities)
    pricing: Pricing | None = None
    adapter: AdapterConfig | None = None
    defaults: Defaults = field(default_factory=Defaults)
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    routing: EndpointRouting = field(default_factory=EndpointRouting)
    upstream_id: str | None = None

    def __post_init__(self, provider: str | None, endpoint: str | None) -> None:
        if self.upstream_id is not None and (
            not isinstance(self.upstream_id, str) or not self.upstream_id.strip()
        ):
            raise ValueError("model upstream_id must be a non-empty string")
        if not self._endpoint_key and provider is not None and endpoint is not None:
            object.__setattr__(
                self,
                "_endpoint_key",
                build_endpoint_key(provider, endpoint),
            )

    @property
    def provider_id(self) -> str:
        return parse_endpoint_key(self._endpoint_key)[0]

    @property
    def endpoint_id(self) -> str:
        return parse_endpoint_key(self._endpoint_key)[1]

    @property
    def input(self) -> tuple[Modality, ...]:
        return self.capabilities.input

    @property
    def output(self) -> tuple[Modality, ...]:
        return self.capabilities.output

    @property
    def context_window(self) -> int | None:
        return self.capabilities.context_window

    @property
    def max_tokens(self) -> int | None:
        return self.capabilities.max_tokens

    @property
    def reasoning(self) -> bool:
        return self.capabilities.reasoning

    @property
    def supports_tool_use(self) -> bool:
        return self.capabilities.tool_use

    @property
    def supports_structured_output(self) -> bool:
        return self.capabilities.structured_output

    @property
    def supports_attachment(self) -> bool:
        return self.capabilities.attachment

    @property
    def supports_temperature(self) -> bool:
        return self.capabilities.temperature

    @property
    def supports_stream(self) -> bool:
        return self.capabilities.stream

    @property
    def supports_thinking(self) -> bool:
        return self.capabilities.supports_thinking

    @property
    def supports_image_input(self) -> bool:
        return self.capabilities.supports_image_input

    @property
    def supports_image_output(self) -> bool:
        return self.capabilities.supports_image_output

    async def stream(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import stream

        return await stream(self, context, options=options, registry=registry)

    async def complete(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import complete

        return await complete(self, context, options=options, registry=registry)

    async def stream_simple(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import stream_simple

        return await stream_simple(self, context, options=options, registry=registry)

    async def complete_simple(self, context, options=None, *, registry=None):
        from loushang.ai.api.streaming import complete_simple

        return await complete_simple(self, context, options=options, registry=registry)

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "displayName": self.name,
            "family": self.family,
            "alias": self.alias,
            "knowledge": self.knowledge,
            "releaseDate": self.release_date,
            "lastUpdated": self.last_updated,
            "defaults": self.defaults.to_raw(),
        }
        raw.update(self.capabilities.to_raw())
        if self.adapter is not None:
            raw["adapter"] = self.adapter.to_raw()
        if self.pricing is not None:
            raw["pricing"] = self.pricing.to_raw()
        if self.auth is not None:
            raw["auth"] = self.auth.to_raw()
        if self.upstream_id is not None:
            raw["upstreamId"] = self.upstream_id
        transport_raw = self.transport.to_raw()
        if transport_raw:
            raw["transport"] = transport_raw
        routing_raw = self.routing.to_raw()
        if routing_raw:
            raw["routing"] = routing_raw
        return {key: value for key, value in raw.items() if value is not None}


@dataclass(frozen=True)
class Endpoint:
    id: str
    api: str
    _provider_key: str = ""
    provider: InitVar[str | None] = None
    name: str | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    region: str | None = None
    lane: str | None = None
    preferred: bool = False
    docs: str | None = None
    auth: Auth | None = None
    defaults: Defaults = field(default_factory=Defaults)
    models: dict[str, Model] = field(default_factory=dict)
    adapter: AdapterConfig | None = None
    transport: EndpointTransport = field(default_factory=EndpointTransport)
    routing: EndpointRouting = field(default_factory=EndpointRouting)

    def __post_init__(self, provider: str | None) -> None:
        if self._provider_key:
            return
        if provider is None:
            return
        object.__setattr__(self, "_provider_key", provider)

    @property
    def provider_id(self) -> str:
        return self._provider_key

    @property
    def endpoint_key(self) -> str:
        return build_endpoint_key(self.provider_id, self.id)

    def get_model(self, model_id: str) -> Model | None:
        return self.models.get(model_id)

    def list_models(self) -> list[Model]:
        return sorted(self.models.values(), key=lambda item: item.id)

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "api": self.api,
            "defaults": self.defaults.to_raw(),
            "models": {
                model_id: model.to_raw() for model_id, model in self.models.items()
            },
        }
        if self.name is not None:
            raw["displayName"] = self.name
        if self.base_url is not None:
            raw["baseUrl"] = self.base_url
        if self.base_url_env is not None:
            raw["baseUrlEnv"] = self.base_url_env
        if self.region is not None:
            raw["region"] = self.region
        if self.lane is not None:
            raw["lane"] = self.lane
        if self.preferred:
            raw["preferred"] = self.preferred
        if self.docs is not None:
            raw["docs"] = self.docs
        if self.auth is not None:
            raw["auth"] = self.auth.to_raw()
        if self.adapter is not None:
            raw["adapter"] = self.adapter.to_raw()
        transport_raw = self.transport.to_raw()
        if transport_raw:
            raw["transport"] = transport_raw
        routing_raw = self.routing.to_raw()
        if routing_raw:
            raw["routing"] = routing_raw
        return raw


@dataclass(frozen=True)
class Provider:
    id: str
    name: str | None = None
    website: str | None = None
    auth: Auth | None = None
    endpoints: dict[str, Endpoint] = field(default_factory=dict)

    def get_endpoint(self, endpoint_id: str) -> Endpoint | None:
        return self.endpoints.get(endpoint_id)

    def list_endpoints(self) -> list[Endpoint]:
        return sorted(self.endpoints.values(), key=lambda item: item.id)

    def get_model(self, endpoint_id: str, model_id: str) -> Model | None:
        endpoint = self.get_endpoint(endpoint_id)
        if endpoint is None:
            return None
        return endpoint.get_model(model_id)

    def list_models(self) -> list[Model]:
        models: list[Model] = []
        for endpoint in self.list_endpoints():
            models.extend(endpoint.list_models())
        return models

    def to_raw(self) -> dict[str, object]:
        raw: dict[str, object] = {
            "endpoints": {
                endpoint_id: endpoint.to_raw()
                for endpoint_id, endpoint in self.endpoints.items()
            }
        }
        if self.name is not None:
            raw["displayName"] = self.name
        if self.website is not None:
            raw["website"] = self.website
        if self.auth is not None:
            raw["auth"] = self.auth.to_raw()
        return raw


def _parse_modalities(raw: object) -> tuple[Modality, ...]:
    if isinstance(raw, str):
        values = tuple(
            value.strip()
            for value in raw.split(",")
            if value.strip() in ALLOWED_MODALITIES
        )
        return _coerce_modalities(values)
    if isinstance(raw, (list, tuple)):
        values = tuple(
            value.strip()
            for value in raw
            if isinstance(value, str) and value.strip() in ALLOWED_MODALITIES
        )
        return _coerce_modalities(values)
    return ("text",)


def _as_optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_optional_number(value: object) -> float | int | None:
    return (
        value
        if not isinstance(value, bool)
        and isinstance(value, int | float)
        and isfinite(value)
        else None
    )


def _as_number(value: object) -> float | int:
    return value if isinstance(value, int | float) else 0


def _as_str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, entry in value.items():
        if isinstance(key, str) and isinstance(entry, str):
            result[key] = entry
    return result


def _as_optional_str_dict(value: object) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str | None] = {}
    for key, entry in value.items():
        if isinstance(key, str) and (entry is None or isinstance(entry, str)):
            result[key] = entry
    return result


def _mapping_or_none(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _coerce_modalities(values: tuple[str, ...]) -> tuple[Modality, ...]:
    return tuple(
        cast(Modality, value) for value in values if value in ALLOWED_MODALITIES
    ) or ("text",)


def build_endpoint_key(provider_id: str, endpoint_id: str) -> str:
    return f"{provider_id}:{endpoint_id}"


def parse_endpoint_key(endpoint_key: str) -> tuple[str, str]:
    if ":" not in endpoint_key:
        return "", endpoint_key
    provider_id, endpoint_id = endpoint_key.split(":", 1)
    return provider_id, endpoint_id
