"""Offline platform quota query example."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from loushang.ai import (
    EndpointQuotaQuery,
    get_model,
    platform_quota_payload,
    query_platform_quota,
)


class _OfflineQuotaTransport:
    async def get_json(
        self,
        query: EndpointQuotaQuery,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> Mapping[str, object]:
        del headers, timeout
        return {
            "usage": {
                "limit": 1000,
                "used": 320,
                "remaining": 680,
                "resetTime": "2026-06-29T00:00:00Z",
            },
            "source": query.endpoint,
        }


async def inspect_platform_quota() -> dict[str, object]:
    model = get_model("moonshot", "coding", "kimi-for-coding")
    quota = await query_platform_quota(
        model,
        api_key="offline-demo-key",
        transport=_OfflineQuotaTransport(),
    )
    return platform_quota_payload(quota)


def main() -> None:
    print(json.dumps(asyncio.run(inspect_platform_quota()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
