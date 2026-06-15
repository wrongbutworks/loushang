from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loushang.tui.core import RenderConstraints, RenderLine, RenderResult
from loushang.tui.theme import ThemeResolver

DirectoryTreeRealKind = Literal["directory", "file"]
DirectoryTreeEntryKind = Literal["directory", "file", "empty", "error", "sentinel"]

PathFilter = Callable[[Path], bool]
PathSortKey = Callable[[Path], object]

__all__ = [
    "DirectoryTree",
    "DirectoryTreeEntry",
    "DirectoryTreeEntryKind",
    "DirectoryTreeRealKind",
    "DirectoryTreeSelect",
    "PathFilter",
    "PathSortKey",
]


@dataclass(frozen=True, slots=True)
class DirectoryTreeEntry:
    path: Path | None
    kind: DirectoryTreeEntryKind
    label: str
    disabled: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class DirectoryTreeSelect:
    path: Path
    kind: DirectoryTreeRealKind


@dataclass(init=False, slots=True)
class DirectoryTree:
    root: str | Path
    show_hidden: bool = False
    path_filter: PathFilter | None = None
    ignore_matcher: PathFilter | None = None
    sort_key: PathSortKey | None = None
    empty_text: str = "No files"
    max_entries: int = 2000
    wrap: bool = True
    theme: ThemeResolver | None = None
    focused: bool = False
    _root_path: Path = field(init=False, repr=False)
    _active_path: Path | None = field(default=None, init=False, repr=False)
    _initial_expanded_paths: tuple[Path, ...] = field(default=(), init=False, repr=False)

    def __init__(
        self,
        root: str | Path,
        active_path: str | Path | None = None,
        expanded_paths: Sequence[str | Path] = (),
        show_hidden: bool = False,
        path_filter: PathFilter | None = None,
        ignore_matcher: PathFilter | None = None,
        sort_key: PathSortKey | None = None,
        empty_text: str = "No files",
        max_entries: int = 2000,
        wrap: bool = True,
        theme: ThemeResolver | None = None,
        focused: bool = False,
    ) -> None:
        self.root = root
        self.show_hidden = show_hidden
        self.path_filter = path_filter
        self.ignore_matcher = ignore_matcher
        self.sort_key = sort_key
        self.empty_text = empty_text
        self.max_entries = max(1, max_entries)
        self.wrap = wrap
        self.theme = theme
        self.focused = focused
        self._root_path = _normalize_absolute_lexical(Path(root), label="root")
        if not self._root_path.exists():
            raise ValueError(f"DirectoryTree root is missing: {self._root_path}")
        if not self._root_path.is_dir():
            raise ValueError(f"DirectoryTree root is not a directory: {self._root_path}")
        self._active_path = (
            None if active_path is None else self._normalize_under_root(Path(active_path), label="active_path")
        )
        self._initial_expanded_paths = tuple(
            self._normalize_under_root(Path(path), label="expanded_paths") for path in expanded_paths
        )

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def active_path(self) -> Path | None:
        return self._active_path

    def _normalize_under_root(self, path: Path, *, label: str) -> Path:
        normalized = _normalize_absolute_lexical(path, label=label)
        try:
            normalized.relative_to(self._root_path)
        except ValueError as exc:
            raise ValueError(f"{label} must be under DirectoryTree root") from exc
        return normalized

    def render(self, constraints: RenderConstraints) -> RenderResult:
        label = self._root_path.name or str(self._root_path)
        return RenderResult.from_lines([RenderLine(label)][: constraints.max_height], constraints=constraints)


def _normalize_absolute_lexical(path: Path, *, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    if ".." in path.parts:
        raise ValueError(f"{label} must not contain '..' path segments")
    return Path(*path.parts)
