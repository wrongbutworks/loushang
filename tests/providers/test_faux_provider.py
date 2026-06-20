from __future__ import annotations

import asyncio

from loushang.ai.model import Model
from loushang.ai.providers.faux import FauxProvider
from loushang.ai.types import UserMessage


def test_faux_provider_stream_resolves_request_when_omitted() -> None:
    provider = FauxProvider()
    model = Model(
        id="faux-model",
        provider="faux",
        endpoint="anthropic-messages",
        api="anthropic-messages",
    )

    stream = asyncio.run(
        provider.stream(
            model,
            {"messages": [UserMessage(role="user", content="hello", timestamp=0.0)]},
            None,
        )
    )
    message = asyncio.run(stream.result())

    assert message.api == "anthropic-messages"
    assert message.provider == "faux"
    assert message.model == "faux-model"
