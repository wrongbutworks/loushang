from __future__ import annotations

import ast
import inspect
import runpy
import shutil
from pathlib import Path
from typing import Any

import pytest

from loushang.tui import (
    CursorDeclaration,
    DirectoryTree,
    DirectoryTreeEntry,
    DirectoryTreeEntryKind,
    DirectoryTreeRealKind,
    DirectoryTreeSelect,
    InputEvent,
    PathFilter,
    PathSortKey,
    RenderConstraints,
    ThemeResolver,
    strip_control_sequences,
)
from loushang.tui.ui_parts import DirectoryTree as UiDirectoryTree
from loushang.tui.ui_parts.widgets import DirectoryTree as WidgetDirectoryTree
from tests.tui.widget_example_playback import play_example


def render_plain(part: Any, *, width: int = 50, height: int = 10) -> tuple[str, ...]:
    result = part.render(RenderConstraints(width=width, max_height=height))
    return tuple(strip_control_sequences(line.text).rstrip() for line in result.lines)


def test_directory_tree_is_reexported_from_public_modules(tmp_path: Path) -> None:
    tree = DirectoryTree(root=tmp_path)

    assert DirectoryTree is UiDirectoryTree
    assert DirectoryTree is WidgetDirectoryTree
    assert DirectoryTreeEntry(path=tmp_path, kind="directory", label=tmp_path.name).path == tmp_path
    assert DirectoryTreeSelect(path=tmp_path, kind="directory").kind == "directory"
    assert DirectoryTreeRealKind is not None
    assert DirectoryTreeEntryKind is not None
    assert PathFilter is not None
    assert PathSortKey is not None
    assert tree.root_path == tmp_path


def test_directory_tree_requires_explicit_absolute_root(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        DirectoryTree()  # type: ignore[call-arg]

    with pytest.raises(ValueError, match="absolute"):
        DirectoryTree(root=Path("relative"))

    with pytest.raises(ValueError, match=r"\.\."):
        DirectoryTree(root=tmp_path / ".." / tmp_path.name)


def test_directory_tree_rejects_missing_and_file_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="missing"):
        DirectoryTree(root=tmp_path / "missing")

    file_root = tmp_path / "file.txt"
    file_root.write_text("data", encoding="utf-8")

    with pytest.raises(ValueError, match="directory"):
        DirectoryTree(root=file_root)


def test_directory_tree_rejects_relative_outside_and_dotdot_public_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        DirectoryTree(root=root, active_path=Path("relative"))
    with pytest.raises(ValueError):
        DirectoryTree(root=root, active_path=tmp_path / "outside")
    with pytest.raises(ValueError):
        DirectoryTree(root=root, active_path=root / ".." / "root")
    with pytest.raises(ValueError):
        DirectoryTree(root=root, expanded_paths=(Path("relative"),))


def test_directory_tree_tui_widget_has_no_coding_imports() -> None:
    import loushang.tui.ui_parts.widgets.directory_tree as module

    source = ast.parse(inspect.getsource(module))
    imports: list[str] = []
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    assert not any(name == "loushang.coding" or name.startswith("loushang.coding.") for name in imports)
