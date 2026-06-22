from __future__ import annotations

import json
import os
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from loushang.ai.auth import storage
from loushang.ai.auth.storage import (
    CredentialStore,
    CredentialStoreCorruptError,
    find_scoped_credential,
    set_scoped_credential,
)
from loushang.ai.auth.types import OAuthCredentials


def _credential(provider: str = "demo") -> OAuthCredentials:
    return OAuthCredentials(
        provider=provider,
        access_token=f"{provider}-access-token",
        refresh_token=f"{provider}-refresh-token",
    )


def _empty_store():
    return {"providers": {}, "endpoints": {}, "models": {}}


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_credential_store_creates_private_directory_and_file(tmp_path) -> None:
    path = tmp_path / "home" / ".loushang" / "ai" / "oauth.json"
    store = CredentialStore(path)

    store.save({"providers": {"demo": _credential()}, "endpoints": {}, "models": {}})

    assert store.load()["providers"]["demo"].access_token == "demo-access-token"
    if os.name == "posix":
        assert _mode(path.parent) == 0o700
        assert _mode(path) == 0o600
        assert _mode(path.with_name("oauth.json.lock")) == 0o600


def test_credential_store_does_not_chmod_existing_custom_parent(tmp_path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX mode assertion")
    tmp_path.chmod(0o755)

    CredentialStore(tmp_path / "oauth.json").save(
        {"providers": {"demo": _credential()}, "endpoints": {}, "models": {}}
    )

    assert _mode(tmp_path) == 0o755


def test_credential_store_writes_by_atomic_replace(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "oauth.json"
    replace_calls: list[tuple[str, str]] = []
    real_replace = storage.os.replace

    def _replace(src, dst) -> None:
        replace_calls.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", _replace)

    CredentialStore(path).save(
        {"providers": {"demo": _credential()}, "endpoints": {}, "models": {}}
    )

    assert replace_calls
    assert replace_calls[0][1] == str(path)
    assert not list(path.parent.glob(".oauth.json.*.tmp"))


def test_credential_store_reports_corrupt_json_with_explicit_error(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CredentialStoreCorruptError, match="not valid JSON"):
        CredentialStore(path).load()


def test_credential_store_reports_structural_corruption(tmp_path) -> None:
    path = tmp_path / "oauth.json"
    path.write_text(json.dumps({"providers": []}), encoding="utf-8")

    with pytest.raises(CredentialStoreCorruptError, match="providers"):
        CredentialStore(path).load()


def test_credential_store_update_merges_concurrent_writes(tmp_path) -> None:
    store = CredentialStore(tmp_path / "oauth.json")
    barrier = threading.Barrier(8)

    def _write(index: int) -> None:
        credential = _credential(f"demo-{index}")
        barrier.wait()

        def _mutate(data) -> None:
            time.sleep(0.01)
            set_scoped_credential(data, credential)

        store.update(_mutate)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(_write, range(8)))

    loaded = store.load()
    assert sorted(loaded["providers"]) == [f"demo-{index}" for index in range(8)]
    assert find_scoped_credential(loaded, "demo-7") == _credential("demo-7")


def test_credential_store_update_can_write_scoped_credentials(tmp_path) -> None:
    store = CredentialStore(tmp_path / "oauth.json")

    def _mutate(data) -> None:
        data.update(_empty_store())
        set_scoped_credential(
            data,
            _credential("demo"),
            endpoint_id="responses",
            model_id="chat",
        )

    store.update(_mutate)

    loaded = store.load()
    assert loaded["models"]["demo:responses:chat"].access_token == "demo-access-token"
