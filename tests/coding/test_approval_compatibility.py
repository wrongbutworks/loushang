from __future__ import annotations

import asyncio


def test_coding_policy_reexports_harness_owned_approval_contracts() -> None:
    import loushang.coding as coding
    import loushang.coding.policy as coding_policy
    import loushang.coding.policy.approval as coding_approval
    import loushang.harness.approval as harness_approval

    owner_symbols = (
        "ApprovalDecision",
        "ApprovalRequest",
        "ApprovalResolver",
        "HeadlessApprovalResolver",
        "resolve_approval",
    )
    coding_top_level_symbols = owner_symbols[:-1]

    for name in owner_symbols:
        assert getattr(coding_approval, name) is getattr(harness_approval, name)
        assert getattr(coding_policy, name) is getattr(harness_approval, name)

    for name in coding_top_level_symbols:
        assert getattr(coding, name) is getattr(harness_approval, name)

    assert coding_approval.DenyApprovalResolver is harness_approval.DenyApprovalResolver
    assert coding_policy.DenyApprovalResolver is harness_approval.DenyApprovalResolver


def test_coding_interactive_approval_resolver_remains_product_owned() -> None:
    import loushang.harness.approval as harness_approval
    from loushang.coding.policy import (
        InteractiveApprovalResolver,
        PolicyEnforcementError,
    )

    assert not hasattr(harness_approval, "InteractiveApprovalResolver")
    assert InteractiveApprovalResolver.__module__ == "loushang.coding.policy.approval"
    assert PolicyEnforcementError.__module__ == "loushang.coding.policy.approval"


def test_coding_interactive_approval_fallback_accepts_harness_resolver() -> None:
    from loushang.coding.policy import InteractiveApprovalResolver
    from loushang.harness.approval import (
        ApprovalDecision,
        ApprovalRequest,
        HeadlessApprovalResolver,
    )

    resolver = InteractiveApprovalResolver(fallback=HeadlessApprovalResolver(mode="allow"))

    decision = asyncio.run(
        resolver.resolve(
            ApprovalRequest(
                tool_name="write",
                arguments={"path": "approved.txt"},
                reason="needs approval",
            )
        )
    )

    assert decision == ApprovalDecision.allow()


def test_coding_resolve_approval_uses_harness_result_validation() -> None:
    import pytest

    from loushang.coding.policy import ApprovalRequest, resolve_approval

    class InvalidResolver:
        def resolve(self, request):
            del request
            return "allow"

    with pytest.raises(TypeError, match="ApprovalResolver returned str"):
        asyncio.run(resolve_approval(InvalidResolver(), ApprovalRequest(tool_name="write", arguments={})))
