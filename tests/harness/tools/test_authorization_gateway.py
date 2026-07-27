from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from loushang.harness.approval import (
    ApprovalDecision,
    HeadlessApprovalResolver,
)
from loushang.harness.authorization import (
    EffectiveExecutionProfile,
    ExecutionAuthorizationError,
)
from loushang.harness.policy import PolicyDecision
from loushang.harness.tools.workspace.authorization import (
    execute_workspace_tool_action,
)


def test_workspace_authorization_gateway_freezes_and_fingerprints_actions() -> None:
    arguments = {"path": "/workspace/file", "edits": [{"old": "a", "new": "b"}]}

    first = asyncio.run(
        execute_workspace_tool_action(
            None,
            tool_name="edit",
            arguments=arguments,
            cwd="/workspace",
            executor=lambda action: action,
        )
    )
    second = asyncio.run(
        execute_workspace_tool_action(
            None,
            tool_name="edit",
            arguments=arguments,
            cwd="/workspace",
            executor=lambda action: action,
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
            execute_workspace_tool_action(
                None,
                tool_name="read",
                arguments={"path": "/outside/secret"},
                cwd="/workspace",
                execution_profile_ceiling=profile,
                executor=lambda _action: pytest.fail("executor must not run"),
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
        execute_workspace_tool_action(
            AskPolicy(),
            tool_name="bash",
            arguments={"command": ("gh", "pr", "create")},
            cwd=str(tmp_path),
            approval_resolver=HeadlessApprovalResolver(mode="allow"),
            execution_profile_ceiling=EffectiveExecutionProfile(
                readable_roots=(tmp_path,),
                writable_roots=(tmp_path,),
            ),
            executor=lambda action: action,
        )
    )

    assert action.execution_profile is not None
    assert action.execution_profile.policy_code == "external_effect"
    assert action.execution_profile.approval_action_id is not None


def test_workspace_gateway_owns_policy_approval_and_execution_order(
    tmp_path: Path,
) -> None:
    events: list[str] = []

    class AskPolicy:
        def evaluate(self, subject):
            del subject
            events.append("policy")
            return PolicyDecision.ask("confirm")

    class Resolver:
        def resolve(self, request):
            del request
            events.append("approval")
            return ApprovalDecision.allow()

    def execute(action):
        events.append("execute")
        return action.fingerprint

    result = asyncio.run(
        execute_workspace_tool_action(
            AskPolicy(),
            tool_name="bash",
            arguments={"command": ("git", "status")},
            cwd=str(tmp_path),
            approval_resolver=Resolver(),
            executor=execute,
        )
    )

    assert events == ["policy", "approval", "execute"]
    assert len(result) == 64


def test_workspace_gateway_revalidates_path_immediately_before_execution(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "notes.txt"
    target.write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    executed = False

    def replace_target(_action):
        target.unlink()
        target.symlink_to(outside)

    def execute(_action):
        nonlocal executed
        executed = True

    with pytest.raises(ExecutionAuthorizationError, match="outside"):
        asyncio.run(
            execute_workspace_tool_action(
                None,
                tool_name="read",
                arguments={"path": str(target)},
                cwd=str(workspace),
                execution_profile_ceiling=EffectiveExecutionProfile(
                    readable_roots=(workspace,),
                ),
                on_authorized=replace_target,
                executor=execute,
            )
        )

    assert executed is False


def test_workspace_gateway_rejects_a_changed_action_fingerprint(
    tmp_path: Path,
) -> None:
    executed = False

    def change_fingerprint(action):
        object.__setattr__(action, "fingerprint", "0" * 64)

    def execute(_action):
        nonlocal executed
        executed = True

    with pytest.raises(ExecutionAuthorizationError, match="changed"):
        asyncio.run(
            execute_workspace_tool_action(
                None,
                tool_name="bash",
                arguments={"command": ("git", "status")},
                cwd=str(tmp_path),
                on_authorized=change_fingerprint,
                executor=execute,
            )
        )

    assert executed is False
