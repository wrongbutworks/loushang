from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

SUPPORTED_IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


@dataclass(frozen=True)
class ClipboardImage:
    bytes: bytes
    mime_type: str


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    stdout: bytes | str = b""


CommandRunner = Callable[..., CommandResult]
NativeClipboardReader = Callable[[], ClipboardImage | None]


def is_wayland_session(env: Mapping[str, str] | None = None) -> bool:
    environment = os.environ if env is None else env
    return bool(environment.get("WAYLAND_DISPLAY")) or environment.get("XDG_SESSION_TYPE") == "wayland"


def extension_for_image_mime_type(mime_type: str) -> str | None:
    match _base_mime_type(mime_type):
        case "image/png":
            return "png"
        case "image/jpeg":
            return "jpg"
        case "image/webp":
            return "webp"
        case "image/gif":
            return "gif"
        case _:
            return None


def read_clipboard_image(
    *,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
    native_reader: NativeClipboardReader | None = None,
    platform_name: str | None = None,
) -> ClipboardImage | None:
    environment = os.environ if env is None else env
    command_runner = _run_command if runner is None else runner
    image: ClipboardImage | None = None
    current_platform = sys.platform if platform_name is None else platform_name
    wsl = _is_wsl(environment, probe_proc=env is None)
    if _is_macos(current_platform):
        image = _read_clipboard_image_via_pngpaste(command_runner)
    if image is None and (is_wayland_session(environment) or wsl):
        image = _read_clipboard_image_via_wl_paste(command_runner) or _read_clipboard_image_via_xclip(command_runner)
    if image is None and wsl:
        image = _read_clipboard_image_via_powershell(command_runner, environment)
    if image is None and not wsl and _is_native_windows(current_platform, environment):
        image = _read_clipboard_image_via_windows_powershell(command_runner, environment)
    if image is None and native_reader is not None:
        image = native_reader()
    if image is None:
        image = _read_clipboard_image_via_xclip(command_runner)
    return _normalize_clipboard_image(image)


def _read_clipboard_image_via_pngpaste(runner: CommandRunner) -> ClipboardImage | None:
    data = runner("pngpaste", ("-",), timeout_seconds=3.0)
    if not data.ok:
        return None
    stdout = _stdout_bytes(data)
    return ClipboardImage(bytes=stdout, mime_type="image/png") if stdout else None


def _read_clipboard_image_via_wl_paste(runner: CommandRunner) -> ClipboardImage | None:
    listed = runner("wl-paste", ("--list-types",), timeout_seconds=1.0)
    if not listed.ok:
        return None
    selected = _select_preferred_image_mime_type(_stdout_text(listed).splitlines())
    if selected is None:
        return None
    data = runner("wl-paste", ("--type", selected, "--no-newline"), timeout_seconds=3.0)
    if not data.ok:
        return None
    stdout = _stdout_bytes(data)
    return ClipboardImage(bytes=stdout, mime_type=_base_mime_type(selected)) if stdout else None


def _read_clipboard_image_via_xclip(runner: CommandRunner) -> ClipboardImage | None:
    targets = runner("xclip", ("-selection", "clipboard", "-t", "TARGETS", "-o"), timeout_seconds=1.0)
    candidate_types: list[str] = []
    if not targets.ok:
        candidate_types = list(SUPPORTED_IMAGE_MIME_TYPES)
    else:
        selected = _select_preferred_image_mime_type(_stdout_text(targets).splitlines())
        candidate_types = _ordered_candidate_types(selected)
    for mime_type in candidate_types:
        data = runner("xclip", ("-selection", "clipboard", "-t", mime_type, "-o"), timeout_seconds=3.0)
        if data.ok:
            stdout = _stdout_bytes(data)
            if stdout:
                return ClipboardImage(bytes=stdout, mime_type=_base_mime_type(mime_type))
    return None


def _read_clipboard_image_via_powershell(runner: CommandRunner, env: Mapping[str, str]) -> ClipboardImage | None:
    path = Path(tempfile.gettempdir()) / f"loushang-wsl-clip-{uuid.uuid4().hex}.png"
    try:
        win_path = runner("wslpath", ("-w", str(path)), timeout_seconds=1.0)
        if not win_path.ok:
            return None
        windows_path = _stdout_text(win_path).strip()
        if not windows_path:
            return None
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$path = $env:LOUSHANG_WSL_CLIPBOARD_IMAGE_PATH; "
            "$img = [System.Windows.Forms.Clipboard]::GetImage(); "
            "if ($img) { $img.Save($path, [System.Drawing.Imaging.ImageFormat]::Png); Write-Output 'ok' } "
            "else { Write-Output 'empty' }"
        )
        result = runner(
            "powershell.exe",
            ("-NoProfile", "-Command", script),
            timeout_seconds=5.0,
            env={**dict(env), "LOUSHANG_WSL_CLIPBOARD_IMAGE_PATH": windows_path},
        )
        if not result.ok or _stdout_text(result).strip() != "ok":
            return None
        if not path.is_file():
            return None
        payload = path.read_bytes()
        return ClipboardImage(bytes=payload, mime_type="image/png") if payload else None
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _read_clipboard_image_via_windows_powershell(runner: CommandRunner, env: Mapping[str, str]) -> ClipboardImage | None:
    path = Path(tempfile.gettempdir()) / f"loushang-win-clip-{uuid.uuid4().hex}.png"
    try:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$path = $env:LOUSHANG_CLIPBOARD_IMAGE_PATH; "
            "$img = [System.Windows.Forms.Clipboard]::GetImage(); "
            "if ($img) { $img.Save($path, [System.Drawing.Imaging.ImageFormat]::Png); Write-Output 'ok' } "
            "else { Write-Output 'empty' }"
        )
        for command in ("powershell.exe", "powershell"):
            result = runner(
                command,
                ("-NoProfile", "-Command", script),
                timeout_seconds=5.0,
                env={**dict(env), "LOUSHANG_CLIPBOARD_IMAGE_PATH": str(path)},
            )
            if result.ok and _stdout_text(result).strip() == "ok" and path.is_file():
                payload = path.read_bytes()
                return ClipboardImage(bytes=payload, mime_type="image/png") if payload else None
        return None
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _select_preferred_image_mime_type(mime_types: list[str]) -> str | None:
    normalized = [(value.strip(), _base_mime_type(value)) for value in mime_types if value.strip()]
    for preferred in SUPPORTED_IMAGE_MIME_TYPES:
        for raw, base in normalized:
            if base == preferred:
                return raw
    for raw, base in normalized:
        if base.startswith("image/"):
            return raw
    return None


def _ordered_candidate_types(selected: str | None) -> list[str]:
    candidates: list[str] = []
    if selected:
        candidates.append(selected)
    for mime_type in SUPPORTED_IMAGE_MIME_TYPES:
        if mime_type not in candidates:
            candidates.append(mime_type)
    return candidates


def _base_mime_type(mime_type: str) -> str:
    return mime_type.split(";", 1)[0].strip().lower()


def _is_supported_image_mime_type(mime_type: str) -> bool:
    return _base_mime_type(mime_type) in SUPPORTED_IMAGE_MIME_TYPES


def _normalize_clipboard_image(image: ClipboardImage | None) -> ClipboardImage | None:
    if image is None:
        return None
    if _is_supported_image_mime_type(image.mime_type):
        return image
    converted = _convert_to_png(image.bytes)
    return ClipboardImage(bytes=converted, mime_type="image/png") if converted is not None else None


def _convert_to_png(payload: bytes) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(BytesIO(payload)) as image:
            output = BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except Exception:
        return None


def _is_wsl(env: Mapping[str, str], *, probe_proc: bool = True) -> bool:
    if env.get("WSL_DISTRO_NAME") or env.get("WSLENV"):
        return True
    if not probe_proc:
        return False
    try:
        release = Path("/proc/version").read_text(encoding="utf-8").lower()
        return "microsoft" in release or "wsl" in release
    except OSError:
        return False


def _is_macos(platform_name: str) -> bool:
    return platform_name == "darwin"


def _is_native_windows(platform_name: str, env: Mapping[str, str]) -> bool:
    return platform_name.startswith("win") or env.get("OS") == "Windows_NT"


def _stdout_text(result: CommandResult) -> str:
    return result.stdout.decode("utf-8", "replace") if isinstance(result.stdout, bytes) else result.stdout


def _stdout_bytes(result: CommandResult) -> bytes:
    return result.stdout.encode("utf-8") if isinstance(result.stdout, str) else result.stdout


def _run_command(command: str, args: tuple[str, ...], *, timeout_seconds: float = 3.0) -> CommandResult:
    try:
        result = subprocess.run(
            [command, *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError):
        return CommandResult(ok=False)
    return CommandResult(ok=result.returncode == 0, stdout=result.stdout)


__all__ = [
    "ClipboardImage",
    "CommandResult",
    "SUPPORTED_IMAGE_MIME_TYPES",
    "extension_for_image_mime_type",
    "is_wayland_session",
    "read_clipboard_image",
]
