from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest


def _context_provider(cwd: Path):
    from loushang.harness.tools.workspace import ToolContext

    def provide(*, tool_call_id: str) -> ToolContext:
        return ToolContext(tool_call_id=tool_call_id, cwd=str(cwd))

    return provide


def test_workspace_read_tool_executes_without_product_adapter(tmp_path: Path) -> None:
    from loushang.harness.tools.workspace import create_read_tool_definition
    from loushang.harness.tools.workspace.wrapper import wrap_tool_definition

    target = tmp_path / "notes.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    tool = wrap_tool_definition(
        create_read_tool_definition(),
        context_provider=_context_provider(tmp_path),
    )

    result = asyncio.run(tool.execute("read-1", {"path": "notes.txt"}))

    assert result.content[0].text == "alpha\nbeta\n"
    assert result.details["path"] == str(target.resolve())


@dataclass(frozen=True)
class _Decision:
    disposition: Literal["allow", "deny", "ask"]
    reason: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class _DenyReads:
    def evaluate_tool_call(self, *, tool_name, arguments, cwd=None) -> _Decision:
        del arguments, cwd
        return _Decision("deny", f"{tool_name} disabled", "disabled")


def test_workspace_policy_accepts_product_neutral_evaluator(tmp_path: Path) -> None:
    from loushang.harness.tools.workspace import (
        PolicyEnforcementError,
        create_read_tool_definition,
    )
    from loushang.harness.tools.workspace.wrapper import wrap_tool_definition

    (tmp_path / "notes.txt").write_text("content", encoding="utf-8")
    tool = wrap_tool_definition(
        create_read_tool_definition(policy_engine=_DenyReads()),
        context_provider=_context_provider(tmp_path),
    )

    with pytest.raises(PolicyEnforcementError, match="read disabled") as exc_info:
        asyncio.run(tool.execute("read-2", {"path": "notes.txt"}))

    assert exc_info.value.tool_result_details["policy_code"] == "disabled"


def test_workspace_factory_uses_product_neutral_metadata() -> None:
    from loushang.harness.tools.workspace import (
        ALL_TOOL_NAMES,
        create_all_tool_definitions,
    )

    definitions = create_all_tool_definitions()

    assert tuple(definitions) == ALL_TOOL_NAMES
    assert all(
        "coding" not in definition.description.lower()
        for definition in definitions.values()
    )
    assert all(
        definition.prompt_snippet is None
        or "coding" not in definition.prompt_snippet.lower()
        for definition in definitions.values()
    )


def test_workspace_tool_settings_accept_product_policy_factory() -> None:
    from types import SimpleNamespace

    from loushang.harness.tools.workspace import workspace_tool_runtime_settings

    captured: dict[str, object] = {}

    def policy_factory(**kwargs: object) -> object:
        captured.update(kwargs)
        return "policy"

    manager = SimpleNamespace(
        get_tool_settings=lambda: SimpleNamespace(
            blocked_tools=("bash",),
            ask_tools=(),
            blocked_substrings=(),
            ask_substrings=("sudo",),
            blocked_path_substrings=(),
            ask_path_substrings=(),
            approval_mode="deny",
            approval_reason="headless",
        )
    )

    result = workspace_tool_runtime_settings(
        manager,
        policy_factory=policy_factory,
    )

    assert result.policy_engine == "policy"
    assert result.approval_resolver is not None
    assert result.approval_resolver.mode == "deny"
    assert captured["blocked_tools"] == ("bash",)
    assert captured["ask_substrings"] == ("sudo",)
