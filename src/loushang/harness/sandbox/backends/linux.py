from __future__ import annotations

import inspect
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from loushang.harness.environment import HostEnvironment
from loushang.harness.workspace.exec import (
    ExecBackend,
    ExecRequest,
    ExecResult,
    ExecUpdateCallback,
    LocalExecBackend,
)

from ..types import (
    SandboxBackendStatus,
    SandboxScopeDescriptor,
    SandboxScopeRequest,
    SandboxUnavailableError,
)

_CAPABILITIES = frozenset(
    {
        "filesystem_roots",
        "filesystem_denied_roots",
        "network_isolation",
        "private_temporary_directory",
        "subprocess_inheritance",
    }
)
_PLATFORM_READ_ROOTS = (
    Path("/usr"),
    Path("/bin"),
    Path("/sbin"),
    Path("/lib"),
    Path("/lib64"),
    Path("/etc"),
    Path("/nix/store"),
)
_PROBE_TIMEOUT_SECONDS = 3.0

BubblewrapFinder = Callable[[str], str | None]
BubblewrapProbeRunner = Callable[
    [tuple[str, ...], float],
    subprocess.CompletedProcess[str],
]


class LinuxBubblewrapBackend:
    """Linux namespace sandbox implemented by wrapping the common exec backend."""

    backend_id = "linux-bubblewrap"

    def __init__(
        self,
        *,
        bwrap_path: str | Path | None = None,
        executable_finder: BubblewrapFinder = shutil.which,
        probe_runner: BubblewrapProbeRunner | None = None,
        local_backend: ExecBackend | None = None,
    ) -> None:
        self._configured_path = Path(bwrap_path) if bwrap_path is not None else None
        self._executable_finder = executable_finder
        self._probe_runner = probe_runner or _run_probe
        self._local_backend = (
            local_backend if local_backend is not None else LocalExecBackend()
        )
        self._resolved_path: Path | None = None
        self._available = False
        self._closed = False

    def probe(self, environment: HostEnvironment) -> SandboxBackendStatus:
        self._available = False
        self._resolved_path = None
        if environment.os_family != "linux":
            return SandboxBackendStatus(
                backend_id=self.backend_id,
                state="not_applicable",
                reason=f"bubblewrap requires Linux, not {environment.platform_name}",
            )

        path = self._resolve_executable()
        if path is None:
            return SandboxBackendStatus(
                backend_id=self.backend_id,
                state="unavailable",
                reason="bubblewrap executable was not found",
            )
        if not path.is_file() or not os.access(path, os.X_OK):
            return SandboxBackendStatus(
                backend_id=self.backend_id,
                state="unavailable",
                reason=f"bubblewrap executable is not runnable: {path}",
            )

        argv = _build_probe_command(path)
        try:
            completed = self._probe_runner(argv, _PROBE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return SandboxBackendStatus(
                backend_id=self.backend_id,
                state="unavailable",
                reason="bubblewrap namespace probe timed out",
            )
        except OSError as error:
            return SandboxBackendStatus(
                backend_id=self.backend_id,
                state="unavailable",
                reason=f"bubblewrap namespace probe failed: {error}",
            )
        if completed.returncode != 0:
            detail = _safe_probe_detail(completed.stderr)
            reason = "bubblewrap cannot create the required namespaces"
            if detail:
                reason = f"{reason}: {detail}"
            return SandboxBackendStatus(
                backend_id=self.backend_id,
                state="unavailable",
                reason=reason,
            )

        self._resolved_path = path
        self._available = True
        return SandboxBackendStatus(
            backend_id=self.backend_id,
            state="available",
            enforced_capabilities=_CAPABILITIES,
        )

    async def open_scope(
        self,
        request: SandboxScopeRequest,
    ) -> _LinuxBubblewrapScope:
        if self._closed:
            raise RuntimeError("bubblewrap backend is closed")
        if not self._available or self._resolved_path is None:
            raise SandboxUnavailableError(
                "bubblewrap backend must pass its namespace probe before use"
            )
        _validate_scope_request(request)
        return _LinuxBubblewrapScope(
            bwrap_path=self._resolved_path,
            request=request,
            local_backend=self._local_backend,
        )

    async def close(self) -> None:
        self._closed = True

    def _resolve_executable(self) -> Path | None:
        if self._configured_path is not None:
            return self._configured_path.expanduser().resolve(strict=False)
        found = self._executable_finder("bwrap")
        if not found:
            return None
        return Path(found).expanduser().resolve(strict=False)


class _LinuxBubblewrapScope:
    def __init__(
        self,
        *,
        bwrap_path: Path,
        request: SandboxScopeRequest,
        local_backend: ExecBackend,
    ) -> None:
        self._bwrap_path = bwrap_path
        self._request = request
        self._local_backend = local_backend
        self._closed = False
        capabilities = set(_CAPABILITIES)
        if request.network == "allowed":
            capabilities.discard("network_isolation")
        self._descriptor = SandboxScopeDescriptor(
            state="enforcing",
            backend_id=LinuxBubblewrapBackend.backend_id,
            enforced_capabilities=frozenset(capabilities),
        )

    @property
    def descriptor(self) -> SandboxScopeDescriptor:
        return self._descriptor

    async def __call__(
        self,
        request: ExecRequest,
        *,
        signal: object | None = None,
        on_update: ExecUpdateCallback | None = None,
    ) -> ExecResult:
        if self._closed:
            raise RuntimeError("bubblewrap scope is closed")
        if request.effective_environment is None:
            raise ValueError("bubblewrap scope requires a materialized ExecRequest")
        wrapped = replace(
            request,
            command=_build_bubblewrap_command(
                self._bwrap_path,
                self._request,
                request.command,
            ),
        )
        result = self._local_backend(
            wrapped,
            signal=signal,
            on_update=on_update,
        )
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, ExecResult):
            raise TypeError("bubblewrap exec backend must return ExecResult")
        return result

    async def close(self) -> None:
        self._closed = True


def _run_probe(
    argv: tuple[str, ...],
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _build_probe_command(bwrap_path: Path) -> tuple[str, ...]:
    true_command = next(
        (
            candidate
            for candidate in ("/usr/bin/true", "/bin/true")
            if Path(candidate).is_file()
        ),
        "/bin/true",
    )
    return (
        str(bwrap_path),
        "--new-session",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-net",
        "--",
        true_command,
    )


def _build_bubblewrap_command(
    bwrap_path: Path,
    scope: SandboxScopeRequest,
    command: tuple[str, ...],
) -> tuple[str, ...]:
    readable_roots = _collapse_roots(scope.readable_roots)
    writable_roots = _collapse_roots(scope.writable_roots)
    full_write = Path("/") in writable_roots
    full_read = full_write or Path("/") in readable_roots
    platform_roots = () if full_read else _platform_read_roots()

    args = [
        str(bwrap_path),
        "--new-session",
        "--die-with-parent",
    ]
    mounted: list[Path] = []
    created: set[Path] = set()
    if full_write:
        args.extend(("--bind", "/", "/"))
        mounted.append(Path("/"))
    elif full_read:
        args.extend(("--ro-bind", "/", "/"))
        mounted.append(Path("/"))
    else:
        args.extend(("--tmpfs", "/"))
        for root in platform_roots:
            _append_bind(args, root, writable=False, mounted=mounted, created=created)
        for root in readable_roots:
            _append_bind(args, root, writable=False, mounted=mounted, created=created)

    args.extend(("--dev", "/dev", "--proc", "/proc"))
    if not any(
        _paths_intersect(Path("/tmp"), root) for root in readable_roots + writable_roots
    ):
        args.extend(("--tmpfs", "/tmp"))

    for root in writable_roots:
        if root == Path("/") and full_write:
            continue
        _append_bind(args, root, writable=True, mounted=mounted, created=created)

    effective_visible_roots = (
        (Path("/"),)
        if full_read
        else _collapse_roots((*platform_roots, *readable_roots, *writable_roots))
    )
    for root in scope.denied_roots:
        if not _path_is_covered(root, effective_visible_roots):
            continue
        if root.is_dir():
            args.extend(("--tmpfs", str(root), "--remount-ro", str(root)))
        else:
            args.extend(("--ro-bind", "/dev/null", str(root)))

    args.extend(
        (
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
        )
    )
    if scope.network in {"denied", "restricted"}:
        args.append("--unshare-net")
    args.extend(("--chdir", str(scope.cwd), "--"))
    args.extend(command)
    return tuple(args)


def _append_bind(
    args: list[str],
    root: Path,
    *,
    writable: bool,
    mounted: list[Path],
    created: set[Path],
) -> None:
    if not writable and any(
        root == existing or root.is_relative_to(existing) for existing in mounted
    ):
        return
    _append_parent_dirs(args, root, mounted=mounted, created=created)
    args.extend(("--bind" if writable else "--ro-bind", str(root), str(root)))
    mounted.append(root)


def _append_parent_dirs(
    args: list[str],
    root: Path,
    *,
    mounted: list[Path],
    created: set[Path],
) -> None:
    parents = tuple(reversed(root.parents))
    for parent in parents:
        if parent == Path("/"):
            continue
        if any(
            parent == existing or parent.is_relative_to(existing)
            for existing in mounted
        ):
            continue
        if parent in created:
            continue
        args.extend(("--dir", str(parent)))
        created.add(parent)
    if root not in created and not any(
        root == existing or root.is_relative_to(existing) for existing in mounted
    ):
        args.extend(("--dir", str(root)))
        created.add(root)


def _validate_scope_request(request: SandboxScopeRequest) -> None:
    visible_roots = _collapse_roots((*request.readable_roots, *request.writable_roots))
    if not _path_is_covered(request.cwd, visible_roots):
        raise SandboxUnavailableError(
            f"sandbox cwd is outside the admitted roots: {request.cwd}"
        )
    for root in visible_roots:
        if not root.exists():
            raise SandboxUnavailableError(f"sandbox root does not exist: {root}")
        if not root.is_dir():
            raise SandboxUnavailableError(
                f"phase-B bubblewrap roots must be directories: {root}"
            )
    for denied in request.denied_roots:
        if request.cwd == denied or request.cwd.is_relative_to(denied):
            raise SandboxUnavailableError(
                f"sandbox cwd conflicts with denied root: {denied}"
            )
        if any(root == denied or root.is_relative_to(denied) for root in visible_roots):
            raise SandboxUnavailableError(
                f"admitted sandbox root conflicts with denied root: {denied}"
            )
        if _path_is_covered(denied, visible_roots) and not denied.exists():
            raise SandboxUnavailableError(
                f"missing denied roots are not enforceable in phase B: {denied}"
            )


def _platform_read_roots() -> tuple[Path, ...]:
    return tuple(path for path in _PLATFORM_READ_ROOTS if path.exists())


def _collapse_roots(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    collapsed: list[Path] = []
    for root in sorted(set(roots), key=lambda path: (len(path.parts), str(path))):
        if any(
            root == existing or root.is_relative_to(existing) for existing in collapsed
        ):
            continue
        collapsed.append(root)
    return tuple(collapsed)


def _path_is_covered(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def _paths_intersect(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _safe_probe_detail(stderr: str | None) -> str:
    if not stderr:
        return ""
    return " ".join(stderr.strip().split())[:500]


__all__ = ["LinuxBubblewrapBackend"]
