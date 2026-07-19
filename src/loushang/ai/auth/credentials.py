from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class ApiKeyAuth:
    value: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class OAuthBearerAuth:
    access_token: str = field(repr=False)
    extra_headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "extra_headers",
            MappingProxyType(dict(self.extra_headers)),
        )


AuthCredential: TypeAlias = ApiKeyAuth | OAuthBearerAuth


__all__ = [
    "ApiKeyAuth",
    "AuthCredential",
    "OAuthBearerAuth",
]
