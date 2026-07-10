from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


def test_source_info_preserves_string_paths() -> None:
    from loushang.harness.resources.source import SourceInfo

    info = SourceInfo(
        path="/tmp/project/prompts/review.md",
        source="package_resource",
        scope="project",
        origin="package",
        base_dir="/tmp/project/prompts",
    )

    assert info.path == "/tmp/project/prompts/review.md"
    assert info.base_dir == "/tmp/project/prompts"


def test_source_info_preserves_path_objects() -> None:
    from loushang.harness.resources.source import SourceInfo

    path = Path("/tmp/project/extensions/demo.py")
    base_dir = path.parent

    info = SourceInfo(path=path, base_dir=base_dir)

    assert info.path is path
    assert info.base_dir is base_dir


def test_source_info_is_immutable() -> None:
    from loushang.harness.resources.source import SourceInfo

    info = SourceInfo(path="/tmp/project/resource.md")

    with pytest.raises(FrozenInstanceError):
        info.path = "/tmp/other.md"  # type: ignore[misc]
