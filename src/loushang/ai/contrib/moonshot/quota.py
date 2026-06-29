from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

from loushang.ai.model import Model

QuotaAuthMode = Literal["bearer", "x-api-key", "bearer_or_x_api_key"]


@dataclass(frozen=True, slots=True)
class PlatformQuota:
    limit: int | float | None
    used: int | float | None
    remaining: int | float | None
    reset_time: str | None
    source: str
    raw: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EndpointQuotaQuery:
    provider: str
    endpoint: str
    url: str
    method: Literal["GET"] = "GET"
    auth_mode: QuotaAuthMode = "bearer"
    response_kind: Literal["platform_quota"] = "platform_quota"
    user_agent: str = "loushang.ai"

    def headers(self, api_key: str) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if self.auth_mode in {"bearer", "bearer_or_x_api_key"}:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.auth_mode in {"x-api-key", "bearer_or_x_api_key"}:
            headers["x-api-key"] = api_key
        return headers


class PlatformQuotaTransport(Protocol):
    async def get_json(
        self,
        query: EndpointQuotaQuery,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> Mapping[str, object]: ...


class PlatformQuotaError(RuntimeError):
    pass


class PlatformQuotaUnsupportedError(PlatformQuotaError):
    pass


class _HttpxPlatformQuotaTransport:
    async def get_json(
        self,
        query: EndpointQuotaQuery,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> Mapping[str, object]:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(query.url, headers=dict(headers))
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, Mapping):
            raise PlatformQuotaError(
                f"platform quota response must be an object: {query.provider}:{query.endpoint}"
            )
        return payload


def endpoint_quota_query_for_model(model: Model) -> EndpointQuotaQuery | None:
    provider = model.provider_id
    endpoint = model.endpoint_id
    if provider in {"kimi-code", "moonshot"} and endpoint in {
        "coding",
        "kimi-code-anthropic",
    }:
        return EndpointQuotaQuery(
            provider=provider,
            endpoint=endpoint,
            url="https://api.kimi.com/coding/v1/usages",
            auth_mode="bearer_or_x_api_key",
            user_agent="KimiCLI/1.5",
        )
    return None


async def query_platform_quota(
    model: Model,
    *,
    api_key: str,
    timeout: float = 12.0,
    transport: PlatformQuotaTransport | None = None,
) -> PlatformQuota:
    query = endpoint_quota_query_for_model(model)
    if query is None:
        raise PlatformQuotaUnsupportedError(
            f"platform quota query is not configured for endpoint: "
            f"{model.provider_id}:{model.endpoint_id}"
        )
    resolved_transport = transport or _HttpxPlatformQuotaTransport()
    payload = await resolved_transport.get_json(
        query,
        headers=query.headers(api_key),
        timeout=timeout,
    )
    return platform_quota_from_payload(
        payload, source=f"{query.provider}:{query.endpoint}"
    )


def platform_quota_from_payload(
    payload: Mapping[str, object],
    *,
    source: str,
) -> PlatformQuota:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        usage = payload
    return PlatformQuota(
        limit=_optional_number(usage.get("limit")),
        used=_optional_number(usage.get("used")),
        remaining=_optional_number(usage.get("remaining")),
        reset_time=_optional_str(usage.get("resetTime") or usage.get("reset_time")),
        source=source,
        raw=dict(payload),
    )


def platform_quota_payload(quota: PlatformQuota | None) -> dict[str, object]:
    if quota is None:
        return {
            "present": False,
            "limit": None,
            "used": None,
            "remaining": None,
            "resetTime": None,
            "source": None,
        }
    return {
        "present": True,
        "limit": quota.limit,
        "used": quota.used,
        "remaining": quota.remaining,
        "resetTime": quota.reset_time,
        "source": quota.source,
    }


def _optional_number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
