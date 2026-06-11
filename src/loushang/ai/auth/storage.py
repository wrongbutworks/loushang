from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Literal, TypedDict

from loushang.ai.auth.types import OAuthCredentials

CredentialScope = Literal["provider", "endpoint", "model"]


class OAuthCredentialStore(TypedDict):
    providers: dict[str, OAuthCredentials]
    endpoints: dict[str, OAuthCredentials]
    models: dict[str, OAuthCredentials]


def _storage_path() -> str:
    home = os.path.expanduser("~")
    base = os.path.join(home, ".loushang", "ai")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "oauth.json")


def load_credentials() -> Dict[str, OAuthCredentials]:
    return load_credential_store()["providers"]


def save_credentials(creds: Dict[str, OAuthCredentials]) -> None:
    save_credential_store({"providers": dict(creds), "endpoints": {}, "models": {}})


def load_credential_store() -> OAuthCredentialStore:
    path = _storage_path()
    if not os.path.exists(path):
        return _empty_store()
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"OAuth credential store must be an object: {path}")
    return {
        "providers": _load_credential_bucket(raw.get("providers"), "providers"),
        "endpoints": _load_credential_bucket(raw.get("endpoints"), "endpoints"),
        "models": _load_credential_bucket(raw.get("models"), "models"),
    }


def save_credential_store(store: OAuthCredentialStore) -> None:
    path = _storage_path()
    serializable = {
        "providers": _dump_credential_bucket(store.get("providers", {})),
        "endpoints": _dump_credential_bucket(store.get("endpoints", {})),
        "models": _dump_credential_bucket(store.get("models", {})),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def find_scoped_credential(
    store: OAuthCredentialStore,
    provider: str,
    *,
    endpoint_id: str | None = None,
    model_id: str | None = None,
) -> OAuthCredentials | None:
    if model_id and not endpoint_id:
        raise ValueError("OAuth model credential scope requires endpoint_id")
    if endpoint_id and model_id:
        credential = store["models"].get(model_scope_key(provider, endpoint_id, model_id))
        if credential is not None:
            return credential
    if endpoint_id:
        credential = store["endpoints"].get(endpoint_scope_key(provider, endpoint_id))
        if credential is not None:
            return credential
    return store["providers"].get(provider)


def set_scoped_credential(
    store: OAuthCredentialStore,
    credential: OAuthCredentials,
    *,
    endpoint_id: str | None = None,
    model_id: str | None = None,
) -> None:
    provider = credential.provider
    if model_id and not endpoint_id:
        raise ValueError("OAuth model credential scope requires endpoint_id")
    if endpoint_id and model_id:
        store["models"][model_scope_key(provider, endpoint_id, model_id)] = credential
    elif endpoint_id:
        store["endpoints"][endpoint_scope_key(provider, endpoint_id)] = credential
    else:
        store["providers"][provider] = credential


def endpoint_scope_key(provider: str, endpoint_id: str) -> str:
    return f"{provider}:{endpoint_id}"


def model_scope_key(provider: str, endpoint_id: str, model_id: str) -> str:
    return f"{provider}:{endpoint_id}:{model_id}"


def _empty_store() -> OAuthCredentialStore:
    return {"providers": {}, "endpoints": {}, "models": {}}


def _load_credential_bucket(value: object, name: str) -> dict[str, OAuthCredentials]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"OAuth credential bucket must be an object: {name}")
    result: dict[str, OAuthCredentials] = {}
    for key, raw_credential in value.items():
        if not isinstance(key, str) or not isinstance(raw_credential, dict):
            continue
        result[key] = OAuthCredentials(
            provider=str(raw_credential.get("provider") or _provider_from_scope_key(key)),
            access_token=str(raw_credential.get("access_token") or raw_credential.get("access") or ""),
            refresh_token=_optional_str(raw_credential.get("refresh_token") or raw_credential.get("refresh")),
            expires_at=raw_credential.get("expires_at") or raw_credential.get("expires"),
            extra=raw_credential.get("extra") if isinstance(raw_credential.get("extra"), dict) else None,
        )
    return result


def _dump_credential_bucket(creds: dict[str, OAuthCredentials]) -> dict[str, Any]:
    serializable: dict[str, Any] = {}
    for key, value in creds.items():
        if not isinstance(key, str):
            continue
        v = value
        if is_dataclass(v):
            serializable[key] = asdict(v)
        else:
            serializable[key] = dict(v)  # type: ignore[arg-type]
    return serializable


def _provider_from_scope_key(key: str) -> str:
    return key.split(":", 1)[0]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
