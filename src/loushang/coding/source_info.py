from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Literal, Protocol

SourceScope = Literal["user", "project", "temporary"]
SourceOrigin = Literal["package", "top-level"]


@dataclass(frozen=True)
class SourceInfo:
    path: str
    source: str = "filesystem"
    scope: SourceScope = "project"
    origin: SourceOrigin = "top-level"
    base_dir: str | None = None


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
) -> SourceInfo:
    return SourceInfo(
        path=_path_text(path),
        source=source,
        scope=scope,
        origin=origin,
        base_dir=_path_text(base_dir) if base_dir is not None else None,
    )


def source_info_from_resource_descriptor(descriptor: SourceDescriptor) -> SourceInfo:
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
) -> dict[str, object]:
    import loushang
    import loushang.coding as loushang_coding

    loushang_module_file = _module_file(loushang)
    coding_module_file = _module_file(loushang_coding)
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "argv0": argv0 if argv0 is not None else _argv0(),
        "cwd": _path_text(Path.cwd() if cwd is None else Path(cwd).expanduser().resolve(strict=False)),
        "package_name": "loushang",
        "package_version": _package_version("loushang"),
        "loushang_module_file": loushang_module_file,
        "coding_module_file": coding_module_file,
        "import_source": _import_source("loushang", loushang_module_file),
    }


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
