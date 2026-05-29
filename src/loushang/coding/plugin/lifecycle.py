from __future__ import annotations

from pathlib import Path

from loushang.coding.package.source import is_remote_package_source, remote_package_name


def is_remote_plugin_source(source: str | Path) -> bool:
    return is_remote_package_source(source)


def remote_plugin_name(source: str) -> str:
    return remote_package_name(source)
