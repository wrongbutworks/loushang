from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenAICodexRuntimeConfig:
    include_client_request_id: bool = True
    include_conversation_id: bool = False
    prompt_cache_retention: str | None = "in-memory"
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
    current: object | None,
) -> OpenAICodexRuntimeConfig:
    if current is None:
        return OpenAICodexRuntimeConfig()
    if not isinstance(current, OpenAICodexRuntimeConfig):
        raise TypeError(
            "adapter_config for openai-codex-responses must be OpenAICodexRuntimeConfig"
        )
    return current


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
