from __future__ import annotations

import asyncio

from loushang.ai.context import normalize_context
from loushang.ai.model import Model
from loushang.ai.providers.faux import FauxProvider
from loushang.ai.types import UserMessage
from tests.providers._runtime import start_test_provider_stream


def _normalized_context(model, context, options=None):
    pairing_mode = (
        "strict" if getattr(options, "pairing_mode", "strict") == "strict" else "repair"
    )
    return normalize_context(context, model=model, pairing_mode=pairing_mode)


async def _stream(provider, model, context, options=None, request=None):
    return start_test_provider_stream(
        provider,
        model,
        _normalized_context(model, context, options),
        options,
        request=request,
    )


def test_faux_provider_stream_resolves_request_when_omitted() -> None:
    provider = FauxProvider()
    model = Model(
        id="faux-model",
        provider="faux",
        endpoint="anthropic-messages",
        api="anthropic-messages",
    )

    stream = asyncio.run(
        _stream(
            provider,
            model,
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            None,
        )
    )
    message = asyncio.run(stream.result())

    assert message.api == "anthropic-messages"
    assert message.provider == "faux"
    assert message.model == "faux-model"
