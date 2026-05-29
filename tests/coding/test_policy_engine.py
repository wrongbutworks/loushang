from __future__ import annotations


def test_policy_decision_helpers_cover_allow_deny_and_ask() -> None:
    from loushang.coding.policy.types import PolicyDecision

    assert PolicyDecision.allow() == PolicyDecision(disposition="allow", reason=None)
    assert PolicyDecision.deny("blocked") == PolicyDecision(disposition="deny", reason="blocked")
    assert PolicyDecision.ask("needs approval") == PolicyDecision(disposition="ask", reason="needs approval")


def test_policy_engine_denies_blocked_commands() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine(blocked_substrings=["rm -rf", "git reset --hard"])
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/bin/sh", "-lc", "rm -rf /tmp/demo"], cwd="/tmp"),
    )

    assert decision.disposition == "deny"
    assert "rm -rf" in decision.reason


def test_policy_engine_denies_destructive_commands_by_default() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/bin/sh", "-lc", "git reset --hard HEAD~1"], cwd="/tmp"),
    )

    assert decision.disposition == "deny"
    assert "git reset --hard" in decision.reason


def test_policy_engine_denies_absolute_path_executables() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/bin/rm", "-rf", "/tmp"], cwd="/tmp"),
    )

    assert decision.disposition == "deny"
    assert "rm -rf" in decision.reason


def test_policy_engine_allows_safe_readonly_command() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/bin/sh", "-lc", "pwd"], cwd="/tmp"),
    )

    assert decision.disposition == "allow"


def test_policy_engine_asks_for_risky_default_heuristics() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/bin/sh", "-lc", "git push origin main"], cwd="/tmp"),
    )

    assert decision.disposition == "ask"


def test_policy_engine_asks_for_env_wrapped_shell_payload() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["/usr/bin/env", "bash", "-lc", "git push origin main"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "ask"


def test_policy_engine_asks_for_env_wrapped_shell_payload_with_assignments() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["env", "FOO=1", "bash", "-lc", "git push origin main"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "ask"


def test_policy_engine_asks_for_env_wrapped_shell_payload_with_option_flags() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["env", "-i", "bash", "-lc", "git push origin main"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "ask"


def test_policy_engine_asks_for_env_wrapped_shell_payload_with_split_string_flag() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["env", "-S", "bash -lc 'git push origin main'"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "ask"


def test_policy_engine_asks_for_env_wrapped_shell_payload_with_unset_option() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["env", "-u", "DEBUG", "bash", "-lc", "git push origin main"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "ask"


def test_policy_engine_allows_env_wrapped_malformed_split_string_without_crashing() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["env", "-S", "'"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "allow"


def test_policy_engine_denies_env_wrapped_malformed_split_string_with_destructive_payload() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["env", "-S", "bash -lc 'rm -rf /tmp"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "deny"


def test_policy_engine_asks_for_absolute_path_git_push() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/usr/bin/git", "push", "origin", "main"], cwd="/tmp"),
    )

    assert decision.disposition == "ask"


def test_policy_engine_denies_sudo_wrapped_destructive_command() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["sudo", "/bin/rm", "-rf", "/tmp"], cwd="/tmp"),
    )

    assert decision.disposition == "deny"


def test_policy_engine_denies_sudo_wrapped_destructive_command_with_options() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["sudo", "-u", "root", "/bin/rm", "-rf", "/tmp"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "deny"


def test_policy_engine_denies_sudo_wrapped_destructive_command_with_prompt_option() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["sudo", "-p", "prompt", "/bin/rm", "-rf", "/tmp"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "deny"


def test_policy_engine_denies_sudo_wrapped_destructive_command_with_chroot_option() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["sudo", "-R", "/chroot", "/bin/rm", "-rf", "/tmp"],
            cwd="/tmp",
        ),
    )

    assert decision.disposition == "deny"


def test_policy_engine_preserves_default_ask_rules_when_customized() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine(ask_substrings=["curl | sh"])
    decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(command=["/bin/sh", "-lc", "git push origin main"], cwd="/tmp"),
    )

    assert decision.disposition == "ask"


def test_policy_engine_uses_shell_payload_with_trailing_args() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()

    deny_decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["/bin/sh", "-lc", "rm -rf /tmp/demo", "ignored", "still-ignored"],
            cwd="/tmp",
        ),
    )
    ask_decision = engine.evaluate_action(
        tool_name="bash",
        exec_request=ExecRequest(
            command=["/bin/sh", "-lc", "git push origin main", "ignored", "still-ignored"],
            cwd="/tmp",
        ),
    )

    assert deny_decision.disposition == "deny"
    assert ask_decision.disposition == "ask"


def test_policy_engine_ignores_literal_substrings_in_direct_argv_commands() -> None:
    from loushang.coding.exec import ExecRequest
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    decision = engine.evaluate_action(
        tool_name="python",
        exec_request=ExecRequest(command=["python", "-c", 'print("rm -rf")'], cwd="/tmp"),
    )

    assert decision.disposition == "allow"


def test_policy_engine_rejects_bare_string_constructor_inputs() -> None:
    from loushang.coding.policy import PolicyEngine

    try:
        PolicyEngine(blocked_substrings="rm -rf")  # type: ignore[arg-type]
    except TypeError as exc:
        assert "blocked_substrings" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected TypeError")


def test_policy_engine_evaluates_generic_tool_name_rules() -> None:
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine(blocked_tools=["write"], ask_tools=["edit"])

    deny_decision = engine.evaluate_tool_call(
        tool_name="write",
        arguments={"path": "notes.txt", "content": "hello"},
        cwd="/tmp/project",
    )
    ask_decision = engine.evaluate_tool_call(
        tool_name="edit",
        arguments={"path": "notes.txt", "edits": [{"oldText": "a", "newText": "b"}]},
        cwd="/tmp/project",
    )
    allow_decision = engine.evaluate_tool_call(
        tool_name="read",
        arguments={"path": "notes.txt"},
        cwd="/tmp/project",
    )

    assert deny_decision.disposition == "deny"
    assert deny_decision.code == "tool_blocked"
    assert "write" in (deny_decision.reason or "")
    assert ask_decision.disposition == "ask"
    assert ask_decision.code == "tool_requires_approval"
    assert "edit" in (ask_decision.reason or "")
    assert allow_decision.disposition == "allow"


def test_policy_engine_reuses_bash_heuristics_for_tool_call_arguments() -> None:
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine()
    ask_decision = engine.evaluate_tool_call(
        tool_name="bash",
        arguments={"command": "git push origin main"},
        cwd="/tmp/project",
    )
    deny_decision = engine.evaluate_tool_call(
        tool_name="bash",
        arguments={"command": "rm -rf /tmp/demo"},
        cwd="/tmp/project",
    )

    assert ask_decision.disposition == "ask"
    assert "git push" in (ask_decision.reason or "")
    assert deny_decision.disposition == "deny"
    assert "rm -rf" in (deny_decision.reason or "")


def test_policy_engine_evaluates_resolved_path_substring_rules() -> None:
    from loushang.coding.policy import PolicyEngine

    engine = PolicyEngine(blocked_path_substrings=["/tmp/project/secrets"])

    decision = engine.evaluate_tool_call(
        tool_name="read",
        arguments={"path": "secrets/token.txt"},
        cwd="/tmp/project",
    )

    assert decision.disposition == "deny"
    assert decision.code == "path_blocked"
    assert "/tmp/project/secrets" in (decision.reason or "")
