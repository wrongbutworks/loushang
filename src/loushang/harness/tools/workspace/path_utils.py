from __future__ import annotations

from pathlib import Path

from loushang.harness.workspace.paths import (
    canonicalize_workspace_path,
    expand_user_path,
    normalize_unicode_spaces,
    resolve_path_from_cwd,
    resolve_workspace_path,
    user_input_path_variants,
)


def _normalize_at_prefix(path: str) -> str:
    return path[1:] if path.startswith("@") else path


def _expand_tool_path(path: str) -> str:
    normalized = normalize_unicode_spaces(_normalize_at_prefix(path))
    return str(expand_user_path(normalized))


def expand_path(path: str) -> str:
    return _expand_tool_path(path)


def resolve_to_cwd(path: str, *, cwd: str | None) -> Path:
    return resolve_path_from_cwd(expand_path(path), cwd=cwd)


def resolve_read_path(path: str, *, cwd: str | None) -> Path:
    return resolve_tool_path(path, cwd=cwd)


def resolve_tool_path(path: str, *, cwd: str | None) -> Path:
    if not isinstance(path, str) or not path:
        raise TypeError("path must be a non-empty string")
    return resolve_workspace_path(
        path,
        cwd=cwd,
        normalizers=(_normalize_at_prefix, normalize_unicode_spaces),
        variant_providers=(user_input_path_variants,),
    )


def canonicalize_tool_path(path: str | Path) -> str:
    return str(canonicalize_workspace_path(path))


def expandPath(path: str) -> str:
    return expand_path(path)


def resolveToCwd(path: str, cwd: str | None) -> Path:
    return resolve_to_cwd(path, cwd=cwd)


def resolveReadPath(path: str, cwd: str | None) -> Path:
    return resolve_read_path(path, cwd=cwd)
