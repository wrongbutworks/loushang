from __future__ import annotations

import asyncio
from collections.abc import Mapping

import pytest

import loushang.ai as ai_module
import loushang.ai.types as types_module
import loushang.ai.usage as usage_module
from loushang.ai.contrib.moonshot import (
    EndpointQuotaQuery,
    PlatformQuotaUnsupportedError,
    endpoint_quota_query_for_model,
    platform_quota_payload,
    query_platform_quota,
)
from loushang.ai.model import Model, Pricing
from loushang.ai.pricing import calculate_usage_cost
from loushang.ai.types import Usage
from loushang.ai.usage import usage_payload


class _QuotaTransport:
    def __init__(self) -> None:
        self.query: EndpointQuotaQuery | None = None
        self.headers: Mapping[str, str] | None = None
        self.timeout: float | None = None

    async def get_json(
        self,
        query: EndpointQuotaQuery,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> Mapping[str, object]:
        self.query = query
        self.headers = headers
        self.timeout = timeout
        return {
            "usage": {
                "limit": 1000,
                "used": 250,
                "remaining": 750,
                "resetTime": "2026-06-29T00:00:00Z",
            }
        }


def test_usage_is_the_stable_response_usage_name() -> None:
    usage = Usage(
        input=10,
        output=5,
        cache_read=3,
        cache_write=2,
        total_tokens=20,
        cost=None,
    )

    assert usage_payload(usage) == {
        "present": True,
        "input": 10,
        "output": 5,
        "cacheRead": 3,
        "cacheWrite": 2,
        "totalTokens": 20,
        "cost": None,
    }


def test_removed_usage_observation_aliases_are_not_public_api() -> None:
    assert not hasattr(ai_module, "UsageObservation")
    assert not hasattr(types_module, "UsageObservation")
    assert not hasattr(ai_module, "usage_observation_from_message")
    assert not hasattr(ai_module, "usage_observation_payload")
    assert not hasattr(usage_module, "usage_observation_from_message")
    assert not hasattr(usage_module, "usage_observation_payload")


def test_platform_quota_helpers_are_not_core_usage_api() -> None:
    removed_names = (
        "EndpointQuotaQuery",
        "PlatformQuota",
        "PlatformQuotaError",
        "PlatformQuotaTransport",
        "PlatformQuotaUnsupportedError",
        "endpoint_quota_query_for_model",
        "platform_quota_from_payload",
        "platform_quota_payload",
        "query_platform_quota",
    )

    for name in removed_names:
        assert not hasattr(usage_module, name)


def test_calculate_usage_cost_uses_decimal_internally() -> None:
    cost = calculate_usage_cost(
        Pricing(input=0.1, output=0.2, cache_read=0, cache_write=0),
        Usage(
            input=3,
            output=7,
            cache_read=0,
            cache_write=0,
            total_tokens=10,
            cost=None,
        ),
    )

    assert cost == {
        "input": 0.0000003,
        "output": 0.0000014,
        "cacheRead": 0.0,
        "cacheWrite": 0.0,
        "total": 0.0000017,
    }


def test_endpoint_quota_query_is_endpoint_scoped_for_kimi_coding() -> None:
    model = Model(
        id="kimi-for-coding",
        provider="moonshot",
        endpoint="coding",
        base_url="https://api.kimi.com/coding/v1",
    )

    query = endpoint_quota_query_for_model(model)

    assert query == EndpointQuotaQuery(
        provider="moonshot",
        endpoint="coding",
        url="https://api.kimi.com/coding/v1/usages",
        auth_mode="bearer_or_x_api_key",
        user_agent="KimiCLI/1.5",
    )


def test_query_platform_quota_uses_endpoint_query_transport() -> None:
    model = Model(
        id="kimi-for-coding",
        provider="moonshot",
        endpoint="kimi-code-anthropic",
        base_url="https://api.kimi.com/coding",
    )
    transport = _QuotaTransport()

    quota = asyncio.run(
        query_platform_quota(
            model,
            api_key="test-key",
            timeout=3.5,
            transport=transport,
        )
    )

    assert transport.query is not None
    assert transport.query.url == "https://api.kimi.com/coding/v1/usages"
    assert transport.headers == {
        "Accept": "application/json",
        "Authorization": "Bearer test-key",
        "User-Agent": "KimiCLI/1.5",
        "x-api-key": "test-key",
    }
    assert transport.timeout == 3.5
    assert platform_quota_payload(quota) == {
        "present": True,
        "limit": 1000,
        "used": 250,
        "remaining": 750,
        "resetTime": "2026-06-29T00:00:00Z",
        "source": "moonshot:kimi-code-anthropic",
    }


def test_query_platform_quota_rejects_unconfigured_endpoints() -> None:
    model = Model(id="chat", provider="openai", endpoint="openai-responses")

    with pytest.raises(PlatformQuotaUnsupportedError, match="openai:openai-responses"):
        asyncio.run(query_platform_quota(model, api_key="test-key"))
