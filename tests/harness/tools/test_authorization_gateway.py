from __future__ import annotations

import asyncio

import pytest

from loushang.harness.tools.workspace.authorization import (
    authorize_workspace_tool_action,
)


def test_workspace_authorization_gateway_freezes_and_fingerprints_actions() -> None:
    arguments = {"path": "/workspace/file", "edits": [{"old": "a", "new": "b"}]}

    first = asyncio.run(
        authorize_workspace_tool_action(
            None,
            tool_name="edit",
            arguments=arguments,
            cwd="/workspace",
        )
    )
    second = asyncio.run(
        authorize_workspace_tool_action(
            None,
            tool_name="edit",
            arguments=arguments,
            cwd="/workspace",
        )
    )

    assert first.fingerprint == second.fingerprint
    assert first.arguments["edits"] == ({"old": "a", "new": "b"},)
    with pytest.raises(TypeError):
        first.arguments["path"] = "/other"  # type: ignore[index]
