from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from loushang.ai.model.compat_schema import (
    CODEX_INCLUDE_CLIENT_REQUEST_ID,
    CODEX_INCLUDE_CONVERSATION_ID,
    CODEX_ORIGINATOR,
    CODEX_PROMPT_CACHE_RETENTION,
    CODEX_USER_AGENT,
)
from loushang.ai.provider.runtime_config import AdapterRuntimeConfig

_OPENAI_CODEX_RUNTIME_COMPAT_KEYS = frozenset(
    {
        CODEX_INCLUDE_CLIENT_REQUEST_ID,
        CODEX_INCLUDE_CONVERSATION_ID,
        CODEX_PROMPT_CACHE_RETENTION,
        CODEX_ORIGINATOR,
        CODEX_USER_AGENT,
    }
)


@dataclass(frozen=True)
class OpenAICodexRuntimeConfig(AdapterRuntimeConfig):
    include_client_request_id: bool = False
    include_conversation_id: bool = False
    prompt_cache_retention: str | None = None
    originator: str = "loushang"
    user_agent: str = "loushang"

    def __post_init__(self) -> None:
        _validate_bool_field(
            "include_client_request_id",
            self.include_client_request_id,
        )
        _validate_bool_field(
            "include_conversation_id",
            self.include_conversation_id,
        )
        _validate_optional_str_field(
            "prompt_cache_retention",
            self.prompt_cache_retention,
        )
        _validate_str_field("originator", self.originator)
        _validate_str_field("user_agent", self.user_agent)


def resolve_openai_codex_runtime_config(
    adapter_options: Mapping[str, object],
    current: AdapterRuntimeConfig | None,
) -> OpenAICodexRuntimeConfig:
    codex_compat = _openai_codex_runtime_compat(adapter_options)
    derived = OpenAICodexRuntimeConfig(
        include_client_request_id=_config_bool(
            codex_compat,
            CODEX_INCLUDE_CLIENT_REQUEST_ID,
        ),
        include_conversation_id=_config_bool(
            codex_compat,
            CODEX_INCLUDE_CONVERSATION_ID,
        ),
        prompt_cache_retention=_config_str(
            codex_compat,
            CODEX_PROMPT_CACHE_RETENTION,
        ),
        originator=_config_str(
            codex_compat,
            CODEX_ORIGINATOR,
            default="loushang",
        )
        or "loushang",
        user_agent=_config_str(
            codex_compat,
            CODEX_USER_AGENT,
            default="loushang",
        )
        or "loushang",
    )
    if current is None:
        return derived
    if not isinstance(current, OpenAICodexRuntimeConfig):
        raise TypeError(
            "adapter_config for openai-codex-responses must be OpenAICodexRuntimeConfig"
        )
    _validate_openai_codex_runtime_config_matches_compat(current, codex_compat)
    return current


def _openai_codex_runtime_compat(
    adapter_options: Mapping[str, object],
) -> dict[str, object]:
    return {
        key: value
        for key, value in adapter_options.items()
        if key in _OPENAI_CODEX_RUNTIME_COMPAT_KEYS
    }


def _validate_openai_codex_runtime_config_matches_compat(
    current: OpenAICodexRuntimeConfig,
    codex_compat: Mapping[str, object],
) -> None:
    expected: dict[str, object | None] = {}
    if CODEX_INCLUDE_CLIENT_REQUEST_ID in codex_compat:
        expected["include_client_request_id"] = _config_bool(
            codex_compat,
            CODEX_INCLUDE_CLIENT_REQUEST_ID,
        )
    if CODEX_INCLUDE_CONVERSATION_ID in codex_compat:
        expected["include_conversation_id"] = _config_bool(
            codex_compat,
            CODEX_INCLUDE_CONVERSATION_ID,
        )
    if CODEX_PROMPT_CACHE_RETENTION in codex_compat:
        expected["prompt_cache_retention"] = _config_str(
            codex_compat,
            CODEX_PROMPT_CACHE_RETENTION,
        )
    if CODEX_ORIGINATOR in codex_compat:
        expected["originator"] = (
            _config_str(codex_compat, CODEX_ORIGINATOR, default="loushang")
            or "loushang"
        )
    if CODEX_USER_AGENT in codex_compat:
        expected["user_agent"] = (
            _config_str(codex_compat, CODEX_USER_AGENT, default="loushang")
            or "loushang"
        )
    for field_name, expected_value in expected.items():
        if getattr(current, field_name) != expected_value:
            raise ValueError(
                "adapter_config conflicts with adapter_options for "
                "openai-codex-responses"
            )


def _config_bool(
    values: Mapping[str, object],
    key: str,
    *,
    default: bool = False,
) -> bool:
    if key not in values:
        return default
    value = values[key]
    if isinstance(value, bool):
        return value
    raise ValueError(f"compat key {key} must be boolean")


def _config_str(
    values: Mapping[str, object],
    key: str,
    *,
    default: str | None = None,
) -> str | None:
    if key not in values:
        return default
    value = values[key]
    if value is None:
        return default
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"compat key {key} must be non-empty string")


def _validate_bool_field(field_name: str, value: object) -> None:
    if isinstance(value, bool):
        return
    raise ValueError(f"{field_name} must be boolean")


def _validate_optional_str_field(field_name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, str) and value:
        return
    raise ValueError(f"{field_name} must be non-empty string or None")


def _validate_str_field(field_name: str, value: object) -> None:
    if isinstance(value, str) and value:
        return
    raise ValueError(f"{field_name} must be non-empty string")
