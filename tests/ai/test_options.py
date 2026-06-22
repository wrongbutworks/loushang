from __future__ import annotations

from dataclasses import fields

from loushang.ai import CallOptions as PublicCallOptions
from loushang.ai import ModelCallOptions as PublicModelCallOptions
from loushang.ai import SimpleCallOptions as PublicSimpleCallOptions
from loushang.ai import StreamOptions as PublicStreamOptions
from loushang.ai.advanced import AnthropicOptions as AdvancedAnthropicOptions
from loushang.ai.advanced import (
    OpenAICompletionsOptions as AdvancedOpenAICompletionsOptions,
)
from loushang.ai.options import (
    AnthropicOptions,
    CallOptions,
    ModelCallOptions,
    OpenAICodexResponsesOptions,
    OpenAICompletionsOptions,
    OpenAIResponsesOptions,
    ProviderStreamOptions,
    ReasoningOptions,
    RetryOptions,
    SimpleCallOptions,
    SimpleStreamOptions,
    StreamOptions,
    TimeoutOptions,
    get_max_output_tokens,
    get_reasoning_budget_tokens,
    get_reasoning_effort,
    get_reasoning_summary,
    get_retry_attempts,
    get_retry_max_delay_ms,
    get_timeout_seconds,
    is_reasoning_requested,
    simple_options_to_call_options,
)


def test_call_options_is_public_and_legacy_names_remain_compatible() -> None:
    assert PublicCallOptions is CallOptions
    assert PublicModelCallOptions is CallOptions
    assert PublicStreamOptions is CallOptions
    assert ModelCallOptions is CallOptions
    assert StreamOptions is CallOptions
    assert ProviderStreamOptions is CallOptions
    assert PublicSimpleCallOptions is SimpleCallOptions
    assert SimpleStreamOptions is SimpleCallOptions

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
        "provider_options",
    } <= field_names
    assert "azure_base_url" not in field_names
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
    assert AnthropicOptions is AdvancedAnthropicOptions
    assert OpenAICompletionsOptions is AdvancedOpenAICompletionsOptions
    assert AnthropicOptions.__module__ == "loushang.ai.advanced.options"


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
