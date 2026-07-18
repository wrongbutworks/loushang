from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, distribution
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Protocol

from loushang.harness.resources.source import SourceInfo, SourceOrigin, SourceScope


class SourceDescriptor(Protocol):
    source_path: Path
    source: str
    source_kind: str
    source_scope: str
    source_root: Path | None


def create_source_info(
    path: str | Path,
    *,
    source: str = "filesystem",
    scope: SourceScope = "project",
    origin: SourceOrigin = "top-level",
    base_dir: str | Path | None = None,
) -> SourceInfo[str]:
    return SourceInfo(
        path=_path_text(path),
        source=source,
        scope=scope,
        origin=origin,
        base_dir=_path_text(base_dir) if base_dir is not None else None,
    )


def source_info_from_resource_descriptor(descriptor: SourceDescriptor) -> SourceInfo[str]:
    return create_source_info(
        descriptor.source_path,
        source=descriptor.source or "filesystem",
        scope=_scope_from_descriptor(source_scope=descriptor.source_scope, source_kind=descriptor.source_kind),
        origin=_origin_from_descriptor(source_scope=descriptor.source_scope, source_kind=descriptor.source_kind),
        base_dir=descriptor.source_root if descriptor.source_root is not None else descriptor.source_path.parent,
    )


def executable_source_identity(
    *,
    cwd: str | Path | None = None,
    argv0: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    import loushang
    import loushang.coding as loushang_coding

    resolved_env = env if env is not None else os.environ
    resolved_cwd = Path.cwd() if cwd is None else Path(cwd).expanduser().resolve(strict=False)
    resolved_argv0 = argv0 if argv0 is not None else _argv0()
    loushang_module_file = _module_file(loushang)
    coding_module_file = _module_file(loushang_coding)
    git_info = _git_identity(resolved_cwd)
    return {
        "entrypoint": _resolve_entrypoint(resolved_argv0, resolved_env),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "argv0": resolved_argv0,
        "cwd": _path_text(resolved_cwd),
        "package_name": "loushang",
        "package_version": _package_version("loushang"),
        "module_file": loushang_module_file,
        "package_root": _package_root_from_module_file(loushang_module_file),
        "loushang_module_file": loushang_module_file,
        "coding_module_file": coding_module_file,
        "project_root": git_info["project_root"],
        "git_branch": git_info["git_branch"],
        "git_commit": git_info["git_commit"],
        "virtual_env": resolved_env.get("VIRTUAL_ENV"),
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
        "is_virtual_env": sys.prefix != sys.base_prefix,
        "path_candidates": _path_candidates(resolved_env),
        "import_source": _import_source("loushang", loushang_module_file),
        "install_mode": _install_mode("loushang", loushang_module_file),
    }


def format_source_identity_text(identity: Mapping[str, object]) -> str:
    lines = ["loushang source info"]
    for key in (
        "entrypoint",
        "python_executable",
        "python_version",
        "module_file",
        "package_root",
        "project_root",
        "git_branch",
        "git_commit",
        "cwd",
        "virtual_env",
        "sys_prefix",
        "sys_base_prefix",
        "package_version",
        "install_mode",
    ):
        lines.append(f"{key}: {_display_value(identity.get(key))}")

    lines.append("path_candidates:")
    candidates = identity.get("path_candidates")
    if isinstance(candidates, list) and candidates:
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            lines.append(
                f"  - {_display_value(candidate.get('path'))} "
                f"[{_display_value(candidate.get('status'))}]"
            )
    else:
        lines.append("  <none>")
    return "\n".join(lines)


def _scope_from_descriptor(*, source_scope: object, source_kind: object) -> SourceScope:
    if source_scope == "user":
        return "user"
    if source_kind == "temporary" or source_scope == "temporary":
        return "temporary"
    return "project"


def _origin_from_descriptor(*, source_scope: object, source_kind: object) -> SourceOrigin:
    if source_scope in {"package", "builtin"} or source_kind in {"external_package", "built_in"}:
        return "package"
    return "top-level"


def _path_text(path: str | Path | object) -> str:
    if isinstance(path, Path):
        return path.as_posix()
    if isinstance(path, str):
        return path
    return str(path)


def _argv0() -> str:
    return sys.argv[0] if sys.argv else ""


def _module_file(module: object) -> str:
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return ""
    return Path(str(module_file)).expanduser().resolve(strict=False).as_posix()


def _package_root_from_module_file(module_file: str) -> str | None:
    if not module_file:
        return None
    path = Path(module_file)
    if path.name == "__init__.py" and path.parent.name == "loushang":
        return path.parent.parent.as_posix()
    return path.parent.as_posix()


def _package_version(package_name: str) -> str:
    try:
        return package_version(package_name)
    except PackageNotFoundError:
        return "0.1.0"


def _import_source(package_name: str, module_file: str) -> str:
    if _distribution_is_editable(package_name):
        return "editable"
    if _module_file_is_source_tree(module_file):
        return "source-tree"
    if _module_file_is_installed(module_file):
        return "installed"
    return "unknown"


def _install_mode(package_name: str, module_file: str) -> str:
    if _distribution_is_editable(package_name):
        return "editable"
    if _module_file_is_source_tree(module_file):
        return "source-tree"
    if _module_file_is_installed(module_file):
        return "package"
    return "unknown"


def _distribution_is_editable(package_name: str) -> bool:
    try:
        direct_url = distribution(package_name).read_text("direct_url.json")
    except PackageNotFoundError:
        return False
    if not direct_url:
        return False
    try:
        payload = json.loads(direct_url)
    except json.JSONDecodeError:
        return False
    dir_info = payload.get("dir_info") if isinstance(payload, dict) else None
    return isinstance(dir_info, dict) and dir_info.get("editable") is True


def _module_file_is_source_tree(module_file: str) -> bool:
    if not module_file:
        return False
    path = Path(module_file)
    return any(parent.name == "src" for parent in path.parents)


def _module_file_is_installed(module_file: str) -> bool:
    if not module_file:
        return False
    return any(parent.name in {"site-packages", "dist-packages"} for parent in Path(module_file).parents)


def _resolve_entrypoint(argv0: str, env: Mapping[str, str]) -> str | None:
    if not argv0:
        return None
    if _looks_like_path(argv0):
        return Path(argv0).expanduser().resolve(strict=False).as_posix()
    resolved = shutil.which(argv0, path=env.get("PATH"))
    if resolved:
        return Path(resolved).expanduser().resolve(strict=False).as_posix()
    return argv0


def _looks_like_path(value: str) -> bool:
    return os.sep in value or (os.altsep is not None and os.altsep in value)


def _path_candidates(env: Mapping[str, str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for directory in os.get_exec_path(dict(env)):
        candidate = Path(directory or ".") / "loushang"
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            continue
        path = candidate.expanduser().resolve(strict=False).as_posix()
        if path in seen:
            continue
        seen.add(path)
        active = not candidates
        candidates.append(
            {
                "path": path,
                "status": "active" if active else "shadowed",
                "active": active,
            }
        )
    return candidates


def _git_identity(cwd: Path) -> dict[str, str | None]:
    project_root = _run_git(cwd, "rev-parse", "--show-toplevel")
    if project_root is None:
        return {"project_root": None, "git_branch": None, "git_commit": None}
    branch = _run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = None
    return {
        "project_root": project_root,
        "git_branch": branch,
        "git_commit": _run_git(cwd, "rev-parse", "HEAD"),
    }


def _run_git(cwd: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", cwd.as_posix(), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _display_value(value: object) -> str:
    if value is None or value == "":
        return "<unknown>"
    return str(value)
