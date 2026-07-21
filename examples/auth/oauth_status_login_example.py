"""Run login, credential status, persistence, and logout without network access."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from tempfile import TemporaryDirectory

import loushang.ai.auth as auth
from loushang.ai import FileCredentialStore, OAuthCredential


@dataclass
class ExampleOAuthProvider:
    """Demo adapter; real adapters use AuthlibOAuthProvider for protocol work."""

    id: str = "example-oauth"

    async def login(self, *, authorize=None) -> OAuthCredential:
        del authorize
        return OAuthCredential(
            provider=self.id,
            access_token="demo-access-secret",
            refresh_token="demo-refresh-secret",
            expires_at=4102444800,
        )

    async def refresh(self, credential: OAuthCredential) -> OAuthCredential:
        return credential

    async def revoke(self, credential: OAuthCredential) -> None:
        del credential


async def run() -> dict[str, object]:
    provider = ExampleOAuthProvider()
    with TemporaryDirectory() as directory:
        store = FileCredentialStore(directory)
        before = auth.credential_status(provider, store=store)
        credential = await auth.login(provider, store=store)
        after_login = auth.credential_status(provider, store=store)
        logged_out = await auth.logout(provider, store=store)
        after_logout = auth.credential_status(provider, store=store)
    return {
        "before": before.state,
        "loginReturnedProvider": credential.provider,
        "afterLogin": after_login.state,
        "authenticated": after_login.authenticated,
        "logoutDeletedCredential": logged_out,
        "afterLogout": after_logout.state,
    }


def main() -> None:
    print(json.dumps(asyncio.run(run()), sort_keys=True))


if __name__ == "__main__":
    main()
