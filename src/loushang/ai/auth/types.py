from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, runtime_checkable


@dataclass(frozen=True)
class OAuthCredentials:
    provider: str
    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    extra: dict[str, Any] | None = None


class OAuthAuthInfo(TypedDict, total=False):
    url: str
    instructions: str


class OAuthPrompt(TypedDict, total=False):
    message: str
    placeholder: str
    allow_empty: bool


class OAuthLoginCallbacks(Protocol):
    def on_auth(self, info: OAuthAuthInfo) -> None: ...
    async def on_prompt(self, prompt: OAuthPrompt) -> str: ...
    def on_progress(self, message: str) -> None: ...
    async def on_manual_code_input(self) -> str: ...
    @property
    def signal(self) -> object | None: ...


@runtime_checkable
class OAuthProviderInterface(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...

    async def login(self, callbacks: OAuthLoginCallbacks) -> OAuthCredentials: ...
    async def refresh_token(
        self, credentials: OAuthCredentials
    ) -> OAuthCredentials: ...
    def get_api_key(self, credentials: OAuthCredentials) -> str: ...
    def uses_callback_server(self) -> bool: ...
    def modify_models(
        self, models: list[object], credentials: OAuthCredentials
    ) -> list[object]: ...
