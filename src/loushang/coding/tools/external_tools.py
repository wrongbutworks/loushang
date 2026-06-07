from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tarfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal, Protocol

from .runtime import MaybeAwaitable, resolve_maybe_awaitable

ExternalToolName = Literal["fd", "rg"]
ExternalToolPolicy = Literal["never", "auto", "required"]


class ExternalToolResolver(Protocol):
    def resolve_tool(self, name: ExternalToolName) -> MaybeAwaitable[str | None]: ...


class ExternalToolDownloader(Protocol):
    def download_tool(self, name: ExternalToolName) -> MaybeAwaitable[str | None]: ...


class ExternalToolDownloadTransport(Protocol):
    def get_latest_release(
        self,
        repo: str,
        *,
        user_agent: str,
        timeout_seconds: float,
    ) -> dict[str, object]: ...

    def download_file(
        self,
        url: str,
        destination: Path,
        *,
        timeout_seconds: float,
    ) -> None: ...


@dataclass(frozen=True)
class LocalExternalToolResolver:
    tools_dir: str | Path | None = None

    def resolve_tool(self, name: ExternalToolName) -> str | None:
        managed_path = _managed_binary_path(_external_tools_dir(self.tools_dir), name, platform_name=sys.platform)
        if managed_path.exists():
            return str(managed_path)
        if name == "fd":
            return shutil.which("fd") or shutil.which("fdfind")
        if name == "rg":
            return shutil.which("rg")
        return None


@dataclass
class DownloadingExternalToolResolver:
    base_resolver: ExternalToolResolver | None = None
    downloader: ExternalToolDownloader | None = None
    allow_download: bool = False
    suppress_download_errors: bool = True
    _cache: dict[ExternalToolName, str] = field(default_factory=dict, init=False, repr=False)

    async def resolve_tool(self, name: ExternalToolName) -> str | None:
        if name in self._cache:
            return self._cache[name]
        path = await resolve_external_tool(name, resolver=self.base_resolver)
        if path is not None:
            self._cache[name] = path
            return path
        if not self.allow_download or self.downloader is None:
            return None
        try:
            downloaded_path = await resolve_maybe_awaitable(self.downloader.download_tool(name))
        except Exception:
            if not self.suppress_download_errors:
                raise
            return None
        if downloaded_path is not None:
            self._cache[name] = downloaded_path
        return downloaded_path


@dataclass(frozen=True)
class ToolDownloadConfig:
    display_name: str
    repo: str
    binary_name: str
    system_binary_names: tuple[str, ...]
    tag_prefix: str


@dataclass(frozen=True)
class ManagedExternalToolInstall:
    name: ExternalToolName
    repo: str
    version: str
    asset_name: str
    binary_path: str


EXTERNAL_TOOL_DOWNLOADS: dict[ExternalToolName, ToolDownloadConfig] = {
    "fd": ToolDownloadConfig(
        display_name="fd",
        repo="sharkdp/fd",
        binary_name="fd",
        system_binary_names=("fd", "fdfind"),
        tag_prefix="v",
    ),
    "rg": ToolDownloadConfig(
        display_name="ripgrep",
        repo="BurntSushi/ripgrep",
        binary_name="rg",
        system_binary_names=("rg",),
        tag_prefix="",
    ),
}


@dataclass(frozen=True)
class UrllibExternalToolDownloadTransport:
    def get_latest_release(
        self,
        repo: str,
        *,
        user_agent: str,
        timeout_seconds: float,
    ) -> dict[str, object]:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"User-Agent": user_agent},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def download_file(
        self,
        url: str,
        destination: Path,
        *,
        timeout_seconds: float,
    ) -> None:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            with destination.open("wb") as handle:
                shutil.copyfileobj(response, handle)


@dataclass(frozen=True)
class GitHubReleaseExternalToolDownloader:
    tools_dir: str | Path | None = None
    transport: ExternalToolDownloadTransport | None = None
    platform_name: str | None = None
    architecture: str | None = None
    app_name: str = "loushang"
    network_timeout_seconds: float = 10.0
    download_timeout_seconds: float = 120.0
    install_lock_timeout_seconds: float = 30.0
    install_lock_stale_seconds: float | None = 300.0
    offline: bool | None = None

    def download_tool(self, name: ExternalToolName) -> str | None:
        if _offline_enabled(self.offline):
            return None
        platform_name = self.platform_name or sys.platform
        if platform_name == "android":
            return None
        config = EXTERNAL_TOOL_DOWNLOADS[name]
        tools_dir = _external_tools_dir(self.tools_dir)
        tools_dir.mkdir(parents=True, exist_ok=True)
        binary_path = _managed_binary_path(tools_dir, name, platform_name=platform_name)
        if binary_path.exists():
            return str(binary_path)

        with _ExternalToolInstallLock(
            tools_dir / f".{config.binary_name}.install.lock",
            timeout_seconds=self.install_lock_timeout_seconds,
            stale_seconds=self.install_lock_stale_seconds,
        ):
            if binary_path.exists():
                return str(binary_path)
            transport = self.transport or UrllibExternalToolDownloadTransport()
            release = transport.get_latest_release(
                config.repo,
                user_agent=f"{self.app_name}-coding-agent",
                timeout_seconds=self.network_timeout_seconds,
            )
            version = _release_version(release)
            asset_name = _asset_name(
                name,
                version=version,
                platform_name=platform_name,
                architecture=self.architecture,
            )
            if asset_name is None:
                return None

            archive_path = tools_dir / f".{asset_name}.download"
            install_path = tools_dir / f".{binary_path.name}.installing"
            download_url = (
                f"https://github.com/{config.repo}/releases/download/"
                f"{config.tag_prefix}{version}/{asset_name}"
            )
            extract_dir = _unique_extract_dir(tools_dir, config.binary_name)
            try:
                transport.download_file(
                    download_url,
                    archive_path,
                    timeout_seconds=self.download_timeout_seconds,
                )
                extract_dir.mkdir(parents=True, exist_ok=True)
                _extract_archive(archive_path, extract_dir)
                extracted_binary = _find_binary(extract_dir, binary_path.name)
                if extracted_binary is None:
                    raise FileNotFoundError(f"Binary not found in archive: expected {binary_path.name}")
                os.replace(extracted_binary, install_path)
                if platform_name != "win32":
                    install_path.chmod(install_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                os.replace(install_path, binary_path)
                _write_tool_metadata(
                    tools_dir,
                    name=name,
                    config=config,
                    version=version,
                    asset_name=asset_name,
                    binary_path=binary_path,
                )
                return str(binary_path)
            finally:
                archive_path.unlink(missing_ok=True)
                install_path.unlink(missing_ok=True)
                shutil.rmtree(extract_dir, ignore_errors=True)


async def resolve_external_tool(
    name: ExternalToolName,
    *,
    resolver: ExternalToolResolver | None,
) -> str | None:
    if resolver is None:
        return LocalExternalToolResolver().resolve_tool(name)
    return await resolve_maybe_awaitable(resolver.resolve_tool(name))


async def ensure_external_tool(
    name: ExternalToolName,
    *,
    resolver: ExternalToolResolver | None = None,
    downloader: ExternalToolDownloader | None = None,
    allow_download: bool = False,
) -> str | None:
    if downloader is None:
        if not allow_download:
            return await resolve_external_tool(name, resolver=resolver)
        downloader = GitHubReleaseExternalToolDownloader()
    download_resolver = DownloadingExternalToolResolver(
        base_resolver=resolver,
        downloader=downloader,
        allow_download=allow_download,
    )
    return await download_resolver.resolve_tool(name)


def normalize_external_tool_policy(
    policy: ExternalToolPolicy | None,
    *,
    allow_download: bool = False,
) -> ExternalToolPolicy | None:
    if policy is not None:
        return policy
    if allow_download:
        return "auto"
    return None


def external_tool_resolver_for_policy(
    *,
    resolver: ExternalToolResolver | None,
    downloader: ExternalToolDownloader | None,
    policy: ExternalToolPolicy | None,
    allow_download: bool = False,
) -> ExternalToolResolver | None:
    resolved_policy = normalize_external_tool_policy(
        policy,
        allow_download=allow_download,
    )
    if resolved_policy == "never":
        return None
    if resolved_policy in {"auto", "required"}:
        return DownloadingExternalToolResolver(
            base_resolver=resolver,
            downloader=downloader or GitHubReleaseExternalToolDownloader(),
            allow_download=True,
        )
    if downloader is None and not allow_download:
        return resolver
    return DownloadingExternalToolResolver(
        base_resolver=resolver,
        downloader=downloader,
        allow_download=allow_download,
    )


def external_tool_required_for_policy(
    policy: ExternalToolPolicy | None,
    *,
    require: bool = False,
) -> bool:
    return require or policy == "required"


def external_tools_enabled_for_policy(policy: ExternalToolPolicy | None) -> bool:
    return policy != "never"


def get_managed_external_tool_install(
    name: ExternalToolName,
    *,
    tools_dir: str | Path | None = None,
    platform_name: str | None = None,
) -> ManagedExternalToolInstall | None:
    resolved_tools_dir = _external_tools_dir(tools_dir)
    resolved_platform = platform_name or sys.platform
    binary_path = _managed_binary_path(resolved_tools_dir, name, platform_name=resolved_platform)
    if not binary_path.exists():
        return None

    config = EXTERNAL_TOOL_DOWNLOADS[name]
    metadata_path = _tool_metadata_path(resolved_tools_dir, config)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(metadata, dict):
        return None

    metadata_name = metadata.get("name")
    repo = metadata.get("repo")
    version = metadata.get("version")
    asset_name = metadata.get("asset_name")
    metadata_binary_path = metadata.get("binary_path")
    if (
        metadata_name != name
        or not isinstance(repo, str)
        or not isinstance(version, str)
        or not isinstance(asset_name, str)
        or not isinstance(metadata_binary_path, str)
        or not Path(metadata_binary_path).exists()
    ):
        return None

    return ManagedExternalToolInstall(
        name=name,
        repo=repo,
        version=version,
        asset_name=asset_name,
        binary_path=metadata_binary_path,
    )


def default_external_tools_dir() -> Path:
    configured_bin_dir = os.environ.get("LOUSHANG_CODING_BIN_DIR")
    if configured_bin_dir:
        return Path(configured_bin_dir).expanduser()
    configured_agent_dir = os.environ.get("LOUSHANG_CODING_AGENT_DIR")
    if configured_agent_dir:
        return Path(configured_agent_dir).expanduser() / "bin"
    return Path.home() / ".loushang" / "coding" / "bin"


def _external_tools_dir(tools_dir: str | Path | None) -> Path:
    if tools_dir is None:
        return default_external_tools_dir()
    return Path(tools_dir).expanduser()


def _managed_binary_path(tools_dir: Path, name: ExternalToolName, *, platform_name: str) -> Path:
    suffix = ".exe" if platform_name == "win32" else ""
    return tools_dir / f"{EXTERNAL_TOOL_DOWNLOADS[name].binary_name}{suffix}"


class _ExternalToolInstallLock:
    def __init__(self, path: Path, *, timeout_seconds: float, stale_seconds: float | None) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self._fd: int | None = None

    def __enter__(self) -> "_ExternalToolInstallLock":
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                if _remove_stale_install_lock(self.path, stale_seconds=self.stale_seconds):
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for external tool install lock: {self.path}")
                time.sleep(0.01)

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        self.path.unlink(missing_ok=True)


def _remove_stale_install_lock(path: Path, *, stale_seconds: float | None) -> bool:
    if stale_seconds is None:
        return False
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return True
    if age_seconds <= stale_seconds:
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _tool_metadata_path(tools_dir: Path, config: ToolDownloadConfig) -> Path:
    return tools_dir / f"{config.binary_name}.metadata.json"


def _write_tool_metadata(
    tools_dir: Path,
    *,
    name: ExternalToolName,
    config: ToolDownloadConfig,
    version: str,
    asset_name: str,
    binary_path: Path,
) -> None:
    metadata_path = _tool_metadata_path(tools_dir, config)
    tmp_path = tools_dir / f".{metadata_path.name}.tmp"
    metadata = {
        "asset_name": asset_name,
        "binary_path": str(binary_path),
        "name": name,
        "repo": config.repo,
        "version": version,
    }
    try:
        tmp_path.write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, metadata_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _offline_enabled(offline: bool | None) -> bool:
    if offline is not None:
        return offline
    for env_name in ("LOUSHANG_OFFLINE", "PI_OFFLINE"):
        value = os.environ.get(env_name)
        if value and value.lower() in {"1", "true", "yes"}:
            return True
    return False


def _release_version(release: dict[str, object]) -> str:
    tag_name = release.get("tag_name")
    if not isinstance(tag_name, str) or not tag_name:
        raise ValueError("GitHub release response must include tag_name")
    return tag_name.removeprefix("v")


def _asset_name(
    name: ExternalToolName,
    *,
    version: str,
    platform_name: str,
    architecture: str | None,
) -> str | None:
    arch_name = _normalized_architecture(architecture)
    if name == "fd":
        if platform_name == "darwin":
            return f"fd-v{version}-{arch_name}-apple-darwin.tar.gz"
        if platform_name == "linux":
            return f"fd-v{version}-{arch_name}-unknown-linux-gnu.tar.gz"
        if platform_name == "win32":
            return f"fd-v{version}-{arch_name}-pc-windows-msvc.zip"
    if name == "rg":
        if platform_name == "darwin":
            return f"ripgrep-{version}-{arch_name}-apple-darwin.tar.gz"
        if platform_name == "linux":
            if arch_name == "aarch64":
                return f"ripgrep-{version}-aarch64-unknown-linux-gnu.tar.gz"
            return f"ripgrep-{version}-x86_64-unknown-linux-musl.tar.gz"
        if platform_name == "win32":
            return f"ripgrep-{version}-{arch_name}-pc-windows-msvc.zip"
    return None


def _normalized_architecture(architecture: str | None) -> str:
    if architecture is not None:
        value = architecture
    elif hasattr(os, "uname"):
        value = os.uname().machine
    else:
        value = "x86_64"
    value = value.lower()
    if value in {"x64", "amd64", "x86_64"}:
        return "x86_64"
    if value in {"arm64", "aarch64"}:
        return "aarch64"
    return value


def _unique_extract_dir(tools_dir: Path, binary_name: str) -> Path:
    return Path(mkdtemp(prefix=f"extract_tmp_{binary_name}_", dir=tools_dir))


def _extract_archive(archive_path: Path, extract_dir: Path) -> None:
    archive_name = archive_path.name.removesuffix(".download")
    if archive_name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as archive:
            _safe_extract_tar(archive, extract_dir)
        return
    if archive_name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract_zip(archive, extract_dir)
        return
    raise ValueError(f"Unsupported archive format: {archive_name}")


def _safe_extract_tar(archive: tarfile.TarFile, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    for member in archive.getmembers():
        target = (extract_dir / member.name).resolve()
        if not _is_relative_to(target, root):
            raise ValueError(f"Archive member escapes extraction directory: {member.name}")
    archive.extractall(extract_dir, filter="data")


def _safe_extract_zip(archive: zipfile.ZipFile, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    for member in archive.infolist():
        target = (extract_dir / member.filename).resolve()
        if not _is_relative_to(target, root):
            raise ValueError(f"Archive member escapes extraction directory: {member.filename}")
    archive.extractall(extract_dir)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _find_binary(root: Path, binary_name: str) -> str | None:
    for candidate in root.rglob(binary_name):
        if candidate.is_file():
            return str(candidate)
    return None
