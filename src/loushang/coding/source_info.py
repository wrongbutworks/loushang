"""Coding source-identity adapter.

Resource provenance is owned by ``harness.resources.source`` and runtime
inspection by ``observability.runtime_identity``. This module only declares the
Coding package/module and display convention.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from loushang.observability.runtime_identity import (
    collect_runtime_identity,
)
from loushang.observability.runtime_identity import (
    format_runtime_identity_text as _format_runtime_identity_text,
)


def executable_source_identity(
    *,
    cwd: str | Path | None = None,
    argv0: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, object]:
    import loushang
    import loushang.coding as loushang_coding

    identity = collect_runtime_identity(
        package_name="loushang",
        package_module=loushang,
        executable_name="loushang",
        related_modules={"coding": loushang_coding},
        cwd=cwd,
        argv0=argv0,
        env=env,
    )
    related = identity.pop("related_module_files")
    assert isinstance(related, Mapping)
    identity["loushang_module_file"] = identity["module_file"]
    identity["coding_module_file"] = related.get("coding", "")
    return identity


def format_source_identity_text(identity: Mapping[str, object]) -> str:
    return _format_runtime_identity_text(identity, title="loushang source info")


__all__ = ["executable_source_identity", "format_source_identity_text"]
