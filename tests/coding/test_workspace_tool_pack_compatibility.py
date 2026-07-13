from __future__ import annotations

import importlib


def test_coding_workspace_tool_modules_alias_harness_owners() -> None:
    module_names = (
        "bash",
        "builtin_renderers",
        "context",
        "edit",
        "edit_diff",
        "external_tools",
        "find",
        "grep",
        "ignore",
        "ls",
        "normalize",
        "operations",
        "output_preview",
        "path_utils",
        "policy",
        "presentation",
        "process",
        "protocol",
        "read",
        "runtime",
        "truncate",
        "wrapper",
        "write",
    )

    for module_name in module_names:
        coding_module = importlib.import_module(f"loushang.coding.tools.{module_name}")
        harness_module = importlib.import_module(
            f"loushang.harness.tools.workspace.{module_name}"
        )
        assert coding_module is harness_module


def test_coding_factory_keeps_product_metadata_and_activation() -> None:
    import loushang.harness.tools.workspace as workspace_tools
    from loushang.coding.tools import create_tool_definition
    from loushang.coding.tools.builtins import BUILTIN_TOOL_PACK

    harness_read = workspace_tools.create_tool_definition("read")
    coding_read = create_tool_definition("read")

    assert "coding workspace" not in harness_read.description
    assert "coding workspace" in coding_read.description
    assert BUILTIN_TOOL_PACK.name == "coding.builtin"
    assert not hasattr(workspace_tools, "BUILTIN_TOOL_PACK")


def test_workspace_external_tool_location_accepts_legacy_coding_env(
    tmp_path, monkeypatch
) -> None:
    from loushang.harness.tools.workspace.external_tools import (
        default_external_tools_dir,
    )

    monkeypatch.delenv("LOUSHANG_WORKSPACE_TOOLS_DIR", raising=False)
    monkeypatch.setenv("LOUSHANG_CODING_BIN_DIR", str(tmp_path))

    assert default_external_tools_dir() == tmp_path
