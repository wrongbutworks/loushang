from __future__ import annotations

from loushang.harness.policy_engine import PolicyEngine
from loushang.harness.workspace.exec import ExecRequest


def test_policy_engine_is_product_neutral_and_namespaces_rules() -> None:
    engine = PolicyEngine(
        rule_id_prefix="design",
        blocked_substrings=("rm -rf",),
    )

    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=("/bin/sh", "-lc", "rm -rf /tmp/demo"), cwd="/tmp"
        ),
    )

    assert decision.disposition == "deny"
    assert engine._evaluator.rules[0].id == "design.command.block.0"


def test_policy_engine_accepts_product_specific_tool_and_path_values() -> None:
    engine = PolicyEngine(
        rule_id_prefix="ppt",
        blocked_tools=("write",),
        ask_path_substrings=("/secrets",),
    )

    tool_decision = engine.evaluate_tool_call(
        tool_name="write", arguments={"path": "/tmp/file"}, cwd="/tmp"
    )
    path_decision = engine.evaluate_tool_call(
        tool_name="read", arguments={"path": "/tmp/secrets/key"}, cwd="/tmp"
    )

    assert tool_decision.disposition == "deny"
    assert path_decision.disposition == "ask"
