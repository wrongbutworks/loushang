from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class ApiKeyAuth:
    value: str = field(repr=False)
    header: str | None = None
    prefix: str | None = None


@dataclass(frozen=True, slots=True)
class OAuthBearerAuth:
    access_token: str = field(repr=False)
    header: str | None = None
    prefix: str | None = None


@dataclass(frozen=True, slots=True)
class NoAuth:
    pass


@dataclass(frozen=True, slots=True)
class HeadersAuth:
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


AuthCredential: TypeAlias = ApiKeyAuth | OAuthBearerAuth | NoAuth | HeadersAuth


__all__ = [
    "ApiKeyAuth",
    "AuthCredential",
    "HeadersAuth",
    "NoAuth",
    "OAuthBearerAuth",
]
