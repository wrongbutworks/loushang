from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path


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


def test_clipboard_image_compatibility_exports_share_tui_owner() -> None:
    from loushang.coding.platform import ClipboardImage as PackageClipboardImage
    from loushang.coding.platform import (
        extension_for_image_mime_type as package_extension_for_image_mime_type,
    )
    from loushang.coding.platform import read_clipboard_image as package_reader
    from loushang.coding.platform.clipboard_image import (
        SUPPORTED_IMAGE_MIME_TYPES as compatibility_supported_mime_types,
    )
    from loushang.coding.platform.clipboard_image import (
        ClipboardImage as CompatibilityClipboardImage,
    )
    from loushang.coding.platform.clipboard_image import (
        CommandResult as CompatibilityCommandResult,
    )
    from loushang.coding.platform.clipboard_image import (
        CommandRunner as CompatibilityCommandRunner,
    )
    from loushang.coding.platform.clipboard_image import (
        NativeClipboardReader as CompatibilityNativeClipboardReader,
    )
    from loushang.coding.platform.clipboard_image import (
        extension_for_image_mime_type as compatibility_extension_for_image_mime_type,
    )
    from loushang.coding.platform.clipboard_image import (
        is_wayland_session as compatibility_is_wayland_session,
    )
    from loushang.coding.platform.clipboard_image import (
        read_clipboard_image as compatibility_reader,
    )
    from loushang.tui.clipboard_image import (
        SUPPORTED_IMAGE_MIME_TYPES,
        ClipboardImage,
        CommandResult,
        CommandRunner,
        NativeClipboardReader,
        extension_for_image_mime_type,
        is_wayland_session,
        read_clipboard_image,
    )

    assert ClipboardImage.__module__ == "loushang.tui.clipboard_image"
    assert PackageClipboardImage is ClipboardImage
    assert CompatibilityClipboardImage is ClipboardImage
    assert CompatibilityCommandResult is CommandResult
    assert CompatibilityCommandRunner is CommandRunner
    assert CompatibilityNativeClipboardReader is NativeClipboardReader
    assert compatibility_supported_mime_types is SUPPORTED_IMAGE_MIME_TYPES
    assert compatibility_extension_for_image_mime_type is extension_for_image_mime_type
    assert compatibility_is_wayland_session is is_wayland_session
    assert package_extension_for_image_mime_type is extension_for_image_mime_type
    assert package_reader is read_clipboard_image
    assert compatibility_reader is read_clipboard_image


def test_importing_coding_platform_does_not_eagerly_load_tui() -> None:
    script = """
import sys

import loushang.coding.platform as platform

assert "loushang.tui" not in sys.modules
assert {
    "ClipboardImage",
    "extension_for_image_mime_type",
    "read_clipboard_image",
}.issubset(dir(platform))
assert "loushang.tui" not in sys.modules
"""

    subprocess.run([sys.executable, "-c", script], check=True)


def test_git_branch_handles_invalid_reftable_head_via_git_fallback(tmp_path) -> None:
    from loushang.coding.platform.git import CommandResult, get_git_branch

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/.invalid\n", encoding="utf-8")

    def runner(command: str, args: tuple[str, ...], *, cwd: Path, **kwargs) -> CommandResult:
        assert command == "git"
        assert args == ("--no-optional-locks", "symbolic-ref", "--quiet", "--short", "HEAD")
        assert cwd == tmp_path
        return CommandResult(ok=True, stdout="main")

    assert get_git_branch(tmp_path, runner=runner) == "main"


def test_git_branch_returns_detached_when_branch_cannot_be_resolved(tmp_path) -> None:
    from loushang.coding.platform.git import CommandResult, get_git_branch

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/.invalid\n", encoding="utf-8")

    def runner(command: str, args: tuple[str, ...], *, cwd: Path, **kwargs) -> CommandResult:
        return CommandResult(ok=False)

    assert get_git_branch(tmp_path, runner=runner) == "detached"
