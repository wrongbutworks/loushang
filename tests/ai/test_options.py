from __future__ import annotations

from loushang.ai import ModelCallOptions as PublicModelCallOptions
from loushang.ai import StreamOptions as PublicStreamOptions
from loushang.ai.options import (
    AnthropicOptions,
    ModelCallOptions,
    OpenAICodexResponsesOptions,
    OpenAICompletionsOptions,
    OpenAIResponsesOptions,
    ProviderStreamOptions,
    SimpleStreamOptions,
    StreamOptions,
)


def test_model_call_options_is_public_and_stream_options_remains_compatible() -> None:
    assert PublicModelCallOptions is ModelCallOptions
    assert PublicStreamOptions is ModelCallOptions
    assert StreamOptions is ModelCallOptions
    assert ProviderStreamOptions is ModelCallOptions

    options = StreamOptions(api_key="key", headers={"x-trace": "1"})

    assert isinstance(options, ModelCallOptions)
    assert options.api_key == "key"
    assert options.headers == {"x-trace": "1"}


def test_provider_specific_options_keep_model_call_fields() -> None:
    option_types = (
        AnthropicOptions,
        OpenAICompletionsOptions,
        OpenAIResponsesOptions,
        OpenAICodexResponsesOptions,
        SimpleStreamOptions,
    )

    for option_type in option_types:
        options = option_type(
            api_key="key",
            headers={"x-trace": "1"},
            oauth_credentials={"provider": object()},
        )

        assert isinstance(options, ModelCallOptions)
        assert options.api_key == "key"
        assert options.headers == {"x-trace": "1"}
        assert options.oauth_credentials is not None
