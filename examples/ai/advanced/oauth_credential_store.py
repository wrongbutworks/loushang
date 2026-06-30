"""Offline OAuth credential-store example."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from loushang.ai.auth.storage import (
    CredentialStore,
    find_scoped_credential,
    set_scoped_credential,
)
from loushang.ai.auth.types import OAuthCredentials


def inspect_oauth_credential_store() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "oauth.json"
        store = CredentialStore(path)

        def _write_endpoint_credential(data) -> None:
            set_scoped_credential(
                data,
                OAuthCredentials(
                    provider="demo",
                    access_token="demo-access-token",
                    refresh_token="demo-refresh-token",
                ),
                endpoint_id="responses",
            )

        store.update(_write_endpoint_credential)
        loaded = store.load()
        credential = find_scoped_credential(
            loaded,
            "demo",
            endpoint_id="responses",
        )
        return {
            "credentialScopes": {
                "providers": len(loaded["providers"]),
                "endpoints": len(loaded["endpoints"]),
                "models": len(loaded["models"]),
            },
            "fileMode": _file_mode(path),
            "selectedCredential": "endpoint" if credential is not None else None,
        }


def main() -> None:
    print(json.dumps(inspect_oauth_credential_store(), indent=2, sort_keys=True))


def _file_mode(path: Path) -> str:
    if os.name != "posix":
        return "platform-default"
    return oct(stat.S_IMODE(path.stat().st_mode))


if __name__ == "__main__":
    main()
