from __future__ import annotations

from pathlib import Path
import re
import unicodedata


_UNICODE_SPACES_RE = re.compile(r"[\u00a0\u2000-\u200a\u202f\u205f\u3000]")
_NARROW_NO_BREAK_SPACE = "\u202f"


def _normalize_unicode_spaces(path: str) -> str:
    return _UNICODE_SPACES_RE.sub(" ", path)


def _normalize_at_prefix(path: str) -> str:
    return path[1:] if path.startswith("@") else path


def _expand_tool_path(path: str) -> str:
    normalized = _normalize_unicode_spaces(_normalize_at_prefix(path))
    if normalized == "~":
        return str(Path.home())
    if normalized.startswith("~/"):
        return str(Path.home()) + normalized[1:]
    return normalized


def expand_path(path: str) -> str:
    return _expand_tool_path(path)


def resolve_to_cwd(path: str, *, cwd: str | None) -> Path:
    resolved = Path(expand_path(path))
    if not resolved.is_absolute():
        base = Path(cwd) if cwd is not None else Path.cwd()
        resolved = base / resolved
    return resolved


def resolve_read_path(path: str, *, cwd: str | None) -> Path:
    return resolve_tool_path(path, cwd=cwd)


def _macos_screenshot_path_variant(path: str) -> str:
    return re.sub(r" (AM|PM)\.", rf"{_NARROW_NO_BREAK_SPACE}\1.", path, flags=re.IGNORECASE)


def _curly_quote_path_variant(path: str) -> str:
    return path.replace("'", "\u2019")


def _existing_path_variant(path: Path) -> Path:
    if path.exists():
        return path

    path_text = str(path)
    variants = [
        _macos_screenshot_path_variant(path_text),
        unicodedata.normalize("NFD", path_text),
        _curly_quote_path_variant(path_text),
    ]
    variants.append(_curly_quote_path_variant(variants[1]))

    for variant in variants:
        if variant == path_text:
            continue
        candidate = Path(variant)
        if candidate.exists():
            return candidate
    return path


def resolve_tool_path(path: str, *, cwd: str | None) -> Path:
    if not isinstance(path, str) or not path:
        raise TypeError("path must be a non-empty string")
    resolved = resolve_to_cwd(path, cwd=cwd)
    return _existing_path_variant(resolved).resolve()


def canonicalize_tool_path(path: str | Path) -> str:
    canonical = Path(path)
    if not canonical.is_absolute():
        raise ValueError("path must be absolute")
    return str(canonical.resolve())


def expandPath(path: str) -> str:
    return expand_path(path)


def resolveToCwd(path: str, cwd: str | None) -> Path:
    return resolve_to_cwd(path, cwd=cwd)


def resolveReadPath(path: str, cwd: str | None) -> Path:
    return resolve_read_path(path, cwd=cwd)
