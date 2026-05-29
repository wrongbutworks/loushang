from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from loushang.ai.auth.types import OAuthCredentials


def _storage_path() -> str:
    home = os.path.expanduser("~")
    base = os.path.join(home, ".loushang", "ai")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "oauth.json")


def load_credentials() -> Dict[str, OAuthCredentials]:
    path = _storage_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        result: Dict[str, OAuthCredentials] = {}
        for k, v in raw.items() if isinstance(raw, dict) else []:
            if isinstance(v, dict):
                result[k] = OAuthCredentials(
                    provider=v.get("provider") or k,
                    access_token=v.get("access_token") or v.get("access") or "",
                    refresh_token=v.get("refresh_token") or v.get("refresh"),
                    expires_at=v.get("expires_at") or v.get("expires"),
                    extra=v.get("extra"),
                )
        return result
    except Exception:
        return {}


def save_credentials(creds: Dict[str, OAuthCredentials]) -> None:
    path = _storage_path()
    serializable: Dict[str, Any] = {}
    for k, v in creds.items():
        if is_dataclass(v):
            serializable[k] = asdict(v)
        else:
            serializable[k] = dict(v)  # type: ignore[arg-type]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
