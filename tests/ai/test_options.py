from __future__ import annotations

from dataclasses import fields

import loushang.ai as ai
import loushang.ai.options as options_module
from loushang.ai import CallOptions as PublicCallOptions
from loushang.ai import SimpleCallOptions as PublicSimpleCallOptions
from loushang.ai.advanced import AnthropicOptions as AdvancedAnthropicOptions
from loushang.ai.advanced import (
    OpenAICompletionsOptions as AdvancedOpenAICompletionsOptions,
)
from loushang.ai.advanced import (
    OpenAIResponsesOptions as AdvancedOpenAIResponsesOptions,
)
from loushang.ai.advanced.registry import ApiProviderRegistry
from loushang.ai.contrib.openai_codex import OpenAICodexResponsesOptions
from loushang.ai.options import (
    CallOptions,
    ModelCallOptions,
    ProviderStreamOptions,
    ReasoningOptions,
    RetryOptions,
    SimpleCallOptions,
    SimpleStreamOptions,
    StreamOptions,
    TimeoutOptions,
    get_max_output_tokens,
    get_provider_option,
    get_reasoning_budget_tokens,
    get_reasoning_effort,
    get_reasoning_summary,
    get_retry_attempts,
    get_retry_max_delay_ms,
    get_timeout_seconds,
    is_reasoning_requested,
    simple_options_to_call_options,
)

AnthropicOptions = AdvancedAnthropicOptions
OpenAICompletionsOptions = AdvancedOpenAICompletionsOptions
OpenAIResponsesOptions = AdvancedOpenAIResponsesOptions


def test_call_options_is_public_and_legacy_names_remain_module_compatible() -> None:
    assert PublicCallOptions is CallOptions
    assert ModelCallOptions is CallOptions
    assert StreamOptions is CallOptions
    assert ProviderStreamOptions is CallOptions
    assert PublicSimpleCallOptions is SimpleCallOptions
    assert SimpleStreamOptions is SimpleCallOptions
    assert "ModelCallOptions" not in ai.__all__
    assert "StreamOptions" not in ai.__all__
    assert not hasattr(ai, "ModelCallOptions")
    assert not hasattr(ai, "StreamOptions")

    options = CallOptions(api_key="key", headers={"x-trace": "1"})

    assert isinstance(options, CallOptions)
    assert options.api_key == "key"
    assert options.headers == {"x-trace": "1"}


def test_call_options_signature_is_provider_neutral() -> None:
    field_names = {field.name for field in fields(CallOptions)}

    assert {
        "api_key",
        "headers",
        "max_output_tokens",
        "temperature",
        "reasoning",
        "retry",
        "timeout",
        "cache_retention",
        "session_id",
        "tool_choice",
    } <= field_names
    assert "provider_options" not in field_names
    assert "azure_base_url" not in field_names
    assert "on_payload" not in field_names
    assert "on_response" not in field_names
    assert "service_tier" not in field_names
    assert "text_verbosity" not in field_names


def test_nested_call_option_helpers_support_new_and_legacy_shapes() -> None:
    options = CallOptions(
        max_output_tokens=123,
        reasoning=ReasoningOptions(
            enabled=True,
            effort="high",
            budget_tokens=2048,
            expose_summary=True,
        ),
        retry=RetryOptions(max_attempts=4, max_delay_seconds=2.5),
        timeout=TimeoutOptions(total_seconds=30),
    )

    assert get_max_output_tokens(options) == 123
    assert is_reasoning_requested(options) is True
    assert get_reasoning_effort(options) == "high"
    assert get_reasoning_summary(options) == "auto"
    assert get_reasoning_budget_tokens(options) == 2048
    assert get_retry_attempts(options) == 4
    assert get_retry_max_delay_ms(options) == 2500
    assert get_timeout_seconds(options) == 30

    legacy = OpenAIResponsesOptions(
        max_tokens=64,
        reasoning="medium",
        reasoning_summary="detailed",
        retries=2,
        max_retry_delay_ms=500,
        timeout=10,
    )
    assert get_max_output_tokens(legacy) == 64
    assert get_reasoning_effort(legacy) == "medium"
    assert get_reasoning_summary(legacy) == "detailed"
    assert get_retry_attempts(legacy) == 2
    assert get_retry_max_delay_ms(legacy) == 500
    assert get_timeout_seconds(legacy) == 10


def test_simple_call_options_map_to_call_options_reasoning() -> None:
    simple = SimpleCallOptions(
        api_key="key",
        max_output_tokens=256,
        reasoning="medium",
        thinking_budgets={"medium": 2048},
    )

    options = simple_options_to_call_options(simple)

    assert isinstance(options, CallOptions)
    assert not isinstance(options, SimpleCallOptions)
    assert options.api_key == "key"
    assert options.max_output_tokens == 256
    assert options.reasoning == ReasoningOptions(
        enabled=True,
        effort="medium",
        budget_tokens=2048,
        expose_summary=True,
    )


def test_provider_specific_options_are_advanced_compatibility_types() -> None:
    assert AdvancedAnthropicOptions.__module__ == "loushang.ai.advanced.options"
    assert (
        AdvancedOpenAICompletionsOptions.__module__ == "loushang.ai.advanced.options"
    )
    assert AdvancedOpenAIResponsesOptions.__module__ == "loushang.ai.advanced.options"
    assert ApiProviderRegistry.__module__ == "loushang.ai.api_registry"
    assert not hasattr(options_module, "AnthropicOptions")
    assert not hasattr(options_module, "OpenAICompletionsOptions")
    assert not hasattr(options_module, "OpenAIResponsesOptions")
    assert "AnthropicOptions" not in ai.__all__
    assert "ApiProviderRegistry" not in ai.__all__
    assert not hasattr(ai, "AnthropicOptions")
    assert not hasattr(ai, "ApiProviderRegistry")
    assert "AzureOpenAIResponsesOptions" not in ai.__all__
    assert not hasattr(ai, "AzureOpenAIResponsesOptions")
    assert OpenAICodexResponsesOptions.__module__ == (
        "loushang.ai.contrib.openai_codex.options"
    )
    assert "OpenAICodexResponsesOptions" not in ai.__all__
    assert not hasattr(ai, "OpenAICodexResponsesOptions")
    assert "on_payload" in {field.name for field in fields(AnthropicOptions)}
    assert "on_response" in {field.name for field in fields(OpenAIResponsesOptions)}


def test_provider_hooks_are_not_stable_call_options_fields() -> None:
    marker = object()

    assert get_provider_option(CallOptions(), "on_payload") is None
    assert (
        get_provider_option(OpenAIResponsesOptions(on_payload=marker), "on_payload")
        is marker
    )


def test_provider_specific_options_keep_model_call_fields() -> None:
    option_types = (
        AnthropicOptions,
        OpenAICompletionsOptions,
        OpenAIResponsesOptions,
        OpenAICodexResponsesOptions,
        SimpleCallOptions,
    )

    for option_type in option_types:
        options = option_type(
            api_key="key",
            headers={"x-trace": "1"},
            oauth_credentials={"provider": object()},
        )

        assert isinstance(options, CallOptions)
        assert options.api_key == "key"
        assert options.headers == {"x-trace": "1"}
        assert options.oauth_credentials is not None
