from __future__ import annotations

import json
import os
import stat

from loushang.auth.storage import CredentialStore


def test_credential_store_hardens_existing_file_on_read(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    path.write_text(
        json.dumps(
            {
                "providers": {
                    "demo": {
                        "provider": "demo",
                        "access_token": "token",
                    }
                },
                "endpoints": {},
                "models": {},
            }
        ),
        encoding="utf-8",
    )
    if os.name == "posix":
        path.chmod(0o666)

    store = CredentialStore(path).load()

    assert store["providers"]["demo"].access_token == "token"
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
