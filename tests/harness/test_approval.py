from __future__ import annotations

import asyncio


def test_approval_decision_helpers_cover_allow_and_deny() -> None:
    from loushang.harness.approval import ApprovalDecision

    assert ApprovalDecision.allow() == ApprovalDecision(disposition="allow", reason=None)
    assert ApprovalDecision.deny("blocked") == ApprovalDecision(disposition="deny", reason="blocked")


def test_approval_decision_rejects_invalid_disposition() -> None:
    import pytest

    from loushang.harness.approval import ApprovalDecision

    with pytest.raises(ValueError, match="Unsupported approval decision disposition"):
        ApprovalDecision(disposition="prompt")  # type: ignore[arg-type]


def test_resolve_approval_defaults_to_deny() -> None:
    from loushang.harness.approval import ApprovalRequest, resolve_approval

    decision = asyncio.run(
        resolve_approval(
            None,
            ApprovalRequest(
                tool_name="write",
                arguments={"path": "x"},
                reason="needs approval",
            ),
        )
    )

    assert decision.disposition == "deny"
    assert decision.reason == "needs approval"


def test_resolve_approval_rejects_invalid_resolver_result() -> None:
    import pytest

    from loushang.harness.approval import ApprovalRequest, resolve_approval

    class InvalidResolver:
        def resolve(self, request):
            del request
            return object()

    with pytest.raises(TypeError, match="ApprovalResolver returned object"):
        asyncio.run(
            resolve_approval(
                InvalidResolver(),
                ApprovalRequest(tool_name="write", arguments={}),
            )
        )


def test_headless_approval_resolver_can_allow() -> None:
    from loushang.harness.approval import ApprovalRequest, HeadlessApprovalResolver

    decision = HeadlessApprovalResolver(mode="allow").resolve(
        ApprovalRequest(tool_name="read", arguments={})
    )

    assert decision.disposition == "allow"


def test_headless_approval_resolver_rejects_invalid_mode() -> None:
    import pytest

    from loushang.harness.approval import HeadlessApprovalResolver

    with pytest.raises(ValueError, match="Unsupported headless approval mode"):
        HeadlessApprovalResolver(mode="prompt")  # type: ignore[arg-type]


def test_approval_request_accepts_opaque_policy_context() -> None:
    from loushang.harness.approval import ApprovalRequest

    policy_decision = object()
    request = ApprovalRequest(
        tool_name="bash",
        arguments={"command": "git push"},
        policy_decision=policy_decision,
    )

    assert request.policy_decision is policy_decision
