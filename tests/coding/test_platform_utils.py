from __future__ import annotations

import asyncio
from pathlib import Path


def _tiny_bmp_1x1_red() -> bytes:
    payload = bytearray(58)
    payload[0:2] = b"BM"
    payload[2:6] = (58).to_bytes(4, "little")
    payload[10:14] = (54).to_bytes(4, "little")
    payload[14:18] = (40).to_bytes(4, "little")
    payload[18:22] = (1).to_bytes(4, "little", signed=True)
    payload[22:26] = (1).to_bytes(4, "little", signed=True)
    payload[26:28] = (1).to_bytes(2, "little")
    payload[28:30] = (24).to_bytes(2, "little")
    payload[34:38] = (4).to_bytes(4, "little")
    payload[54] = 0x00
    payload[55] = 0x00
    payload[56] = 0xFF
    return bytes(payload)


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


def test_clipboard_image_reads_wayland_with_xclip_fallback() -> None:
    from loushang.coding.platform.clipboard_image import (
        CommandResult,
        read_clipboard_image,
    )

    calls: list[tuple[str, tuple[str, ...]]] = []

    def runner(command: str, args: tuple[str, ...], **kwargs) -> CommandResult:
        calls.append((command, args))
        if command == "wl-paste":
            return CommandResult(ok=False)
        if command == "xclip" and "TARGETS" in args:
            return CommandResult(ok=True, stdout=b"text/plain\nimage/png\n")
        if command == "xclip" and "image/png" in args:
            return CommandResult(ok=True, stdout=b"PNG")
        return CommandResult(ok=False)

    image = read_clipboard_image(env={"WAYLAND_DISPLAY": "wayland-0"}, runner=runner)

    assert image is not None
    assert image.bytes == b"PNG"
    assert image.mime_type == "image/png"
    assert calls == [
        ("wl-paste", ("--list-types",)),
        ("xclip", ("-selection", "clipboard", "-t", "TARGETS", "-o")),
        ("xclip", ("-selection", "clipboard", "-t", "image/png", "-o")),
    ]


def test_clipboard_image_converts_wayland_bmp_to_png() -> None:
    from loushang.coding.platform.clipboard_image import (
        CommandResult,
        read_clipboard_image,
    )

    def runner(command: str, args: tuple[str, ...], **kwargs) -> CommandResult:
        if command == "wl-paste" and "--list-types" in args:
            return CommandResult(ok=True, stdout=b"image/bmp\n")
        if command == "wl-paste" and "image/bmp" in args:
            return CommandResult(ok=True, stdout=_tiny_bmp_1x1_red())
        return CommandResult(ok=False)

    image = read_clipboard_image(env={"WAYLAND_DISPLAY": "wayland-0"}, runner=runner)

    assert image is not None
    assert image.mime_type == "image/png"
    assert image.bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_clipboard_image_xclip_tries_supported_mimes_when_targets_fail() -> None:
    from loushang.coding.platform.clipboard_image import (
        CommandResult,
        read_clipboard_image,
    )

    calls: list[tuple[str, tuple[str, ...]]] = []

    def runner(command: str, args: tuple[str, ...], **kwargs) -> CommandResult:
        calls.append((command, args))
        if command == "xclip" and "TARGETS" in args:
            return CommandResult(ok=False)
        if command == "xclip" and "image/png" in args:
            return CommandResult(ok=True, stdout=b"PNG")
        return CommandResult(ok=False)

    image = read_clipboard_image(env={}, runner=runner)

    assert image is not None
    assert image.bytes == b"PNG"
    assert image.mime_type == "image/png"
    assert calls[:2] == [
        ("xclip", ("-selection", "clipboard", "-t", "TARGETS", "-o")),
        ("xclip", ("-selection", "clipboard", "-t", "image/png", "-o")),
    ]


def test_clipboard_image_uses_wsl_powershell_fallback(tmp_path) -> None:
    from loushang.coding.platform.clipboard_image import (
        CommandResult,
        read_clipboard_image,
    )

    png_payload = b"\x89PNG\r\n\x1a\npayload"
    calls: list[tuple[str, tuple[str, ...]]] = []

    def runner(command: str, args: tuple[str, ...], **kwargs) -> CommandResult:
        calls.append((command, args))
        if command in {"wl-paste", "xclip"}:
            return CommandResult(ok=False)
        if command == "wslpath":
            return CommandResult(ok=True, stdout=args[1])
        if command == "powershell.exe":
            env = kwargs.get("env") or {}
            Path(env["LOUSHANG_WSL_CLIPBOARD_IMAGE_PATH"]).write_bytes(png_payload)
            return CommandResult(ok=True, stdout=b"ok\n")
        return CommandResult(ok=False)

    image = read_clipboard_image(env={"WSL_DISTRO_NAME": "Ubuntu"}, runner=runner)

    assert image is not None
    assert image.bytes == png_payload
    assert image.mime_type == "image/png"
    assert calls[-2][0] == "wslpath"
    assert calls[-1][0] == "powershell.exe"


def test_clipboard_image_uses_macos_pngpaste_before_xclip() -> None:
    from loushang.coding.platform.clipboard_image import (
        CommandResult,
        read_clipboard_image,
    )

    calls: list[tuple[str, tuple[str, ...]]] = []

    def runner(command: str, args: tuple[str, ...], **kwargs) -> CommandResult:
        calls.append((command, args))
        if command == "pngpaste":
            return CommandResult(ok=True, stdout=b"\x89PNG\r\n\x1a\nmac")
        return CommandResult(ok=False)

    image = read_clipboard_image(env={}, runner=runner, platform_name="darwin")

    assert image is not None
    assert image.bytes == b"\x89PNG\r\n\x1a\nmac"
    assert image.mime_type == "image/png"
    assert calls[0] == ("pngpaste", ("-",))
    assert not any(command == "xclip" for command, _args in calls)


def test_clipboard_image_uses_native_windows_powershell_without_wslpath(tmp_path) -> None:
    from loushang.coding.platform.clipboard_image import (
        CommandResult,
        read_clipboard_image,
    )

    png_payload = b"\x89PNG\r\n\x1a\nwin"
    calls: list[tuple[str, tuple[str, ...]]] = []

    def runner(command: str, args: tuple[str, ...], **kwargs) -> CommandResult:
        calls.append((command, args))
        if command == "powershell.exe":
            env = kwargs.get("env") or {}
            Path(env["LOUSHANG_CLIPBOARD_IMAGE_PATH"]).write_bytes(png_payload)
            return CommandResult(ok=True, stdout=b"ok\n")
        return CommandResult(ok=False)

    image = read_clipboard_image(env={"OS": "Windows_NT"}, runner=runner, platform_name="win32")

    assert image is not None
    assert image.bytes == png_payload
    assert image.mime_type == "image/png"
    assert len(calls) == 1
    assert calls[0][0] == "powershell.exe"
    assert calls[0][1][:2] == ("-NoProfile", "-Command")


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
