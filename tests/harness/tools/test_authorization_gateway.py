from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loushang.harness.approval import HeadlessApprovalResolver
from loushang.harness.authorization import (
    EffectiveExecutionProfile,
    ExecutionAuthorizationError,
)
from loushang.harness.policy import PolicyDecision
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


def test_workspace_gateway_enforces_file_roots_from_execution_profile() -> None:
    profile = EffectiveExecutionProfile(
        readable_roots=(Path("/workspace"),),
    )

    with pytest.raises(ExecutionAuthorizationError, match="outside"):
        asyncio.run(
            authorize_workspace_tool_action(
                None,
                tool_name="read",
                arguments={"path": "/outside/secret"},
                cwd="/workspace",
                execution_profile_ceiling=profile,
            )
        )


def test_workspace_gateway_binds_policy_and_approval_to_execution_profile(
    tmp_path: Path,
) -> None:
    class AskPolicy:
        def evaluate(self, subject):
            del subject
            return PolicyDecision.ask("confirm", code="external_effect")

    action = asyncio.run(
        authorize_workspace_tool_action(
            AskPolicy(),
            tool_name="bash",
            arguments={"command": ("gh", "pr", "create")},
            cwd=str(tmp_path),
            approval_resolver=HeadlessApprovalResolver(mode="allow"),
            execution_profile_ceiling=EffectiveExecutionProfile(
                readable_roots=(tmp_path,),
                writable_roots=(tmp_path,),
            ),
        )
    )

    assert action.execution_profile is not None
    assert action.execution_profile.policy_code == "external_effect"
    assert action.execution_profile.approval_action_id is not None
