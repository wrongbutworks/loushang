from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_IGNORED_DIRS = {".git", "node_modules"}


@dataclass(frozen=True)
class IgnoreRule:
    base: Path
    pattern: str


@dataclass(frozen=True)
class IgnoreMatcher:
    root: Path
    rules: tuple[IgnoreRule, ...]

    @property
    def patterns(self) -> tuple[str, ...]:
        return tuple(rule.pattern for rule in self.rules)

    def is_ignored(self, path: Path) -> bool:
        parts = path.relative_to(self.root).parts
        if any(part in _DEFAULT_IGNORED_DIRS for part in parts):
            return True
        for rule in self.rules:
            try:
                relative_path = path.relative_to(rule.base).as_posix()
            except ValueError:
                continue
            if _matches_gitignore_pattern(relative_path, rule.pattern):
                return True
        return False


def load_ignore_matcher(root: Path) -> IgnoreMatcher:
    rules: list[IgnoreRule] = []
    for gitignore in _iter_gitignore_files(root):
        for line in _read_ignore_patterns(gitignore):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue
            rules.append(IgnoreRule(base=gitignore.parent, pattern=stripped))
    return IgnoreMatcher(root=root, rules=tuple(rules))


def _iter_gitignore_files(root: Path) -> list[Path]:
    gitignore_files: list[Path] = []
    for current_dir, dir_names, file_names in os.walk(root):
        dir_names[:] = [name for name in dir_names if name not in _DEFAULT_IGNORED_DIRS]
        if ".gitignore" in file_names:
            gitignore_files.append(Path(current_dir) / ".gitignore")
    return gitignore_files


def _read_ignore_patterns(gitignore: Path) -> list[str]:
    return gitignore.read_text(encoding="utf-8", errors="ignore").splitlines()


def _matches_gitignore_pattern(relative_path: str, pattern: str) -> bool:
    normalized = pattern.lstrip("/")
    if normalized.endswith("/"):
        prefix = normalized.rstrip("/")
        return relative_path == prefix or relative_path.startswith(f"{prefix}/")
    if "/" in normalized:
        return fnmatch.fnmatch(relative_path, normalized)
    name = relative_path.rsplit("/", 1)[-1]
    return fnmatch.fnmatch(name, normalized) or fnmatch.fnmatch(relative_path, normalized)
