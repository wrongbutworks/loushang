from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from contextlib import contextmanager, suppress
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict, TypeVar

try:  # pragma: no cover - exercised on POSIX in tests.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback.
    fcntl = None  # type: ignore[assignment]

from loushang.ai.auth.types import OAuthCredentials

CredentialScope = Literal["provider", "endpoint", "model"]
T = TypeVar("T")

_PRIVATE_DIR_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_PROCESS_LOCK = threading.RLock()


class OAuthCredentialStore(TypedDict):
    providers: dict[str, OAuthCredentials]
    endpoints: dict[str, OAuthCredentials]
    models: dict[str, OAuthCredentials]


class CredentialStoreError(ValueError):
    """Base error for local OAuth credential store failures."""


class CredentialStoreCorruptError(CredentialStoreError):
    """Raised when the credential store cannot be parsed as a valid store."""


class CredentialStorePermissionError(CredentialStoreError):
    """Raised when the credential store cannot be read or written securely."""


class CredentialStore:
    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._path = Path(path) if path is not None else Path(_storage_path())
        self._harden_existing_parent = path is None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> OAuthCredentialStore:
        _ensure_private_parent(
            self.path.parent,
            harden_existing=self._harden_existing_parent,
        )
        with _locked_credential_path(self.path):
            return _load_credential_store_unlocked(self.path)

    def save(self, store: OAuthCredentialStore) -> None:
        _ensure_private_parent(
            self.path.parent,
            harden_existing=self._harden_existing_parent,
        )
        with _locked_credential_path(self.path):
            _save_credential_store_unlocked(self.path, store)

    def update(self, mutate: Callable[[OAuthCredentialStore], T]) -> T:
        _ensure_private_parent(
            self.path.parent,
            harden_existing=self._harden_existing_parent,
        )
        with _locked_credential_path(self.path):
            store = _load_credential_store_unlocked(self.path)
            result = mutate(store)
            _save_credential_store_unlocked(self.path, store)
            return result


def _storage_path() -> str:
    home = os.path.expanduser("~")
    base = os.path.join(home, ".loushang", "ai")
    return os.path.join(base, "oauth.json")


def load_credentials() -> dict[str, OAuthCredentials]:
    return load_credential_store()["providers"]


def save_credentials(creds: dict[str, OAuthCredentials]) -> None:
    save_credential_store({"providers": dict(creds), "endpoints": {}, "models": {}})


def load_credential_store(
    path: str | os.PathLike[str] | None = None,
) -> OAuthCredentialStore:
    return CredentialStore(path).load()


def save_credential_store(
    store: OAuthCredentialStore,
    path: str | os.PathLike[str] | None = None,
) -> None:
    CredentialStore(path).save(store)


def update_credential_store(
    mutate: Callable[[OAuthCredentialStore], T],
    path: str | os.PathLike[str] | None = None,
) -> T:
    return CredentialStore(path).update(mutate)


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
        credential = store["models"].get(
            model_scope_key(provider, endpoint_id, model_id)
        )
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


def _load_credential_store_unlocked(path: Path) -> OAuthCredentialStore:
    if not path.exists():
        return _empty_store()
    try:
        _chmod_private_file(path)
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as error:
        raise CredentialStoreCorruptError(
            f"OAuth credential store is not valid JSON: {path}"
        ) from error
    except PermissionError as error:
        raise CredentialStorePermissionError(
            f"OAuth credential store cannot be read: {path}"
        ) from error
    except OSError as error:
        raise CredentialStoreError(
            f"OAuth credential store cannot be read: {path}"
        ) from error
    if not isinstance(raw, dict):
        raise CredentialStoreCorruptError(
            f"OAuth credential store must be an object: {path}"
        )
    return {
        "providers": _load_credential_bucket(raw.get("providers"), "providers"),
        "endpoints": _load_credential_bucket(raw.get("endpoints"), "endpoints"),
        "models": _load_credential_bucket(raw.get("models"), "models"),
    }


def _save_credential_store_unlocked(
    path: Path,
    store: OAuthCredentialStore,
) -> None:
    serializable = {
        "providers": _dump_credential_bucket(store.get("providers", {})),
        "endpoints": _dump_credential_bucket(store.get("endpoints", {})),
        "models": _dump_credential_bucket(store.get("models", {})),
    }
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
            text=True,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        _chmod_private_file(Path(tmp_name))
        os.replace(tmp_name, path)
        tmp_name = None
        _chmod_private_file(path)
        _fsync_directory(path.parent)
    except PermissionError as error:
        raise CredentialStorePermissionError(
            f"OAuth credential store cannot be written: {path}"
        ) from error
    except OSError as error:
        raise CredentialStoreError(
            f"OAuth credential store cannot be written: {path}"
        ) from error
    finally:
        if tmp_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(tmp_name)


def _load_credential_bucket(value: object, name: str) -> dict[str, OAuthCredentials]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CredentialStoreCorruptError(
            f"OAuth credential bucket must be an object: {name}"
        )
    result: dict[str, OAuthCredentials] = {}
    for key, raw_credential in value.items():
        if not isinstance(key, str) or not isinstance(raw_credential, dict):
            raise CredentialStoreCorruptError(
                f"OAuth credential entry must be an object: {name}"
            )
        result[key] = OAuthCredentials(
            provider=str(
                raw_credential.get("provider") or _provider_from_scope_key(key)
            ),
            access_token=str(
                raw_credential.get("access_token") or raw_credential.get("access") or ""
            ),
            refresh_token=_optional_str(
                raw_credential.get("refresh_token") or raw_credential.get("refresh")
            ),
            expires_at=raw_credential.get("expires_at")
            or raw_credential.get("expires"),
            extra=raw_credential.get("extra")
            if isinstance(raw_credential.get("extra"), dict)
            else None,
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


def _ensure_private_parent(path: Path, *, harden_existing: bool) -> None:
    try:
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if harden_existing or not existed:
            _chmod_private_dir(path)
    except PermissionError as error:
        raise CredentialStorePermissionError(
            f"OAuth credential store directory cannot be created: {path}"
        ) from error
    except OSError as error:
        raise CredentialStoreError(
            f"OAuth credential store directory cannot be created: {path}"
        ) from error


@contextmanager
def _locked_credential_path(path: Path):
    lock_path = path.with_name(f"{path.name}.lock")
    with _PROCESS_LOCK:
        try:
            fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, _PRIVATE_FILE_MODE)
            _chmod_private_file(lock_path)
        except PermissionError as error:
            raise CredentialStorePermissionError(
                f"OAuth credential store lock cannot be opened: {lock_path}"
            ) from error
        except OSError as error:
            raise CredentialStoreError(
                f"OAuth credential store lock cannot be opened: {lock_path}"
            ) from error
        with os.fdopen(fd, "a+", encoding="utf-8") as lock_file:
            try:
                _lock_file(lock_file.fileno())
            except PermissionError as error:
                raise CredentialStorePermissionError(
                    f"OAuth credential store lock cannot be acquired: {lock_path}"
                ) from error
            except OSError as error:
                raise CredentialStoreError(
                    f"OAuth credential store lock cannot be acquired: {lock_path}"
                ) from error
            try:
                yield
            finally:
                _unlock_file(lock_file.fileno())


def _lock_file(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_file(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _chmod_private_dir(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, _PRIVATE_DIR_MODE)


def _chmod_private_file(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, _PRIVATE_FILE_MODE)


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
