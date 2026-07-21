"""Load a temporary OAuth credential file and call a model offline."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from tempfile import TemporaryDirectory

from loushang.ai import (
    CallOptions,
    FileCredentialStore,
    OAuthCredential,
    complete,
)
from loushang.ai.advanced.registry import (
    clear_api_providers,
    register_api_provider,
    reset_api_providers,
)
from loushang.ai.event_stream.raw_parts import RawPart
from loushang.ai.model import Auth, Capabilities, Model
from loushang.ai.provider import ProviderRequest


class _RecordingProvider:
    api = "auth-example-oauth"

    def __init__(self) -> None:
        self.request: ProviderRequest | None = None

    async def invoke_raw(self, request: ProviderRequest) -> AsyncIterator[RawPart]:
        self.request = request
        yield {"type": "response_start", "response_id": "oauth-example"}
        yield {"type": "text_delta", "text": "ok"}
        yield {"type": "stop_reason", "stop_reason": "stop"}
        yield {"type": "response_done"}


async def run() -> dict[str, object]:
    provider = _RecordingProvider()
    model = Model(
        id="oauth-file-example",
        provider="example",
        endpoint="oauth",
        api=provider.api,
        base_url="https://offline.example/v1",
        auth=Auth(kind="oauth", provider="example-oauth"),
        capabilities=Capabilities(stream=True),
    )
    with TemporaryDirectory() as directory:
        store = FileCredentialStore(directory)
        credential_path = store.save(
            OAuthCredential(
                provider="example-oauth",
                access_token="file-access-secret",
                refresh_token="file-refresh-secret",
                expires_at=4102444800,
                extra_headers={"x-account": "example-account"},
            )
        )
        clear_api_providers()
        register_api_provider(provider)
        try:
            await complete(
                model,
                {"messages": [{"role": "user", "content": "hello"}]},
                CallOptions(credential_file=credential_path),
            )
        finally:
            reset_api_providers()

    if provider.request is None:
        raise RuntimeError("ProviderRequest was not captured")
    return {
        "credentialFile": credential_path.name,
        "authorizationResolved": provider.request.headers.get("Authorization")
        == "Bearer file-access-secret",
        "extraHeaderResolved": provider.request.headers.get("x-account")
        == "example-account",
        "requestAuthType": type(provider.request.options.auth).__name__,
        "lifecycleCredentialCleared": provider.request.options.credential is None,
    }


def main() -> None:
    print(json.dumps(asyncio.run(run()), sort_keys=True))


if __name__ == "__main__":
    main()
