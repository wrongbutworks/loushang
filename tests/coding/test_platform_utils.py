from __future__ import annotations

import asyncio


def test_coding_platform_does_not_export_retired_shared_capabilities() -> None:
    import loushang.coding.platform as platform

    for name in (
        "ClipboardCopyResult",
        "ClipboardImage",
        "copy_to_clipboard",
        "extension_for_image_mime_type",
        "get_git_branch",
        "read_clipboard_image",
    ):
        assert not hasattr(platform, name)
        assert name not in platform.__all__


def test_version_check_compares_package_versions_and_skips_offline(monkeypatch) -> None:
    from loushang.coding.platform.version_check import (
        check_for_new_loushang_version,
        compare_package_versions,
        is_newer_package_version,
    )

    assert compare_package_versions("v1.2.3", "1.2.2") > 0
    assert compare_package_versions("1.2.3-beta", "1.2.3") < 0
    assert is_newer_package_version("not-semver", "1.2.3") is True

    calls: list[object] = []

    async def fetcher(*args, **kwargs):
        calls.append((args, kwargs))
        return {"version": "1.2.4"}

    assert asyncio.run(check_for_new_loushang_version("1.2.3", fetcher=fetcher)) == "1.2.4"
    assert calls[0][0][0] == "https://loushang.ai/api/latest-version"

    monkeypatch.setenv("LOUSHANG_SKIP_VERSION_CHECK", "1")
    assert asyncio.run(check_for_new_loushang_version("1.2.3", fetcher=fetcher)) is None
