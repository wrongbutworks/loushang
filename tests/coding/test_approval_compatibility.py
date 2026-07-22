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


def test_coding_interactive_approval_resolver_uses_shared_lifecycle() -> None:
    import loushang.harness.approval as harness_approval
    from loushang.coding.policy import (
        InteractiveApprovalResolver,
        PolicyEnforcementError,
    )
    from loushang.harness.tools.workspace.policy import (
        PolicyEnforcementError as HarnessPolicyEnforcementError,
    )

    assert hasattr(harness_approval, "InteractiveApprovalResolver")
    assert InteractiveApprovalResolver.__module__ == "loushang.coding.policy.approval"
    assert issubclass(
        InteractiveApprovalResolver,
        harness_approval.InteractiveApprovalResolver,
    )
    assert PolicyEnforcementError is HarnessPolicyEnforcementError


def test_coding_interactive_approval_fallback_accepts_harness_resolver() -> None:
    from loushang.coding.policy import InteractiveApprovalResolver
    from loushang.harness.approval import (
        ApprovalDecision,
        ApprovalRequest,
        HeadlessApprovalResolver,
    )

    resolver = InteractiveApprovalResolver(
        fallback=HeadlessApprovalResolver(mode="allow")
    )

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


def test_coding_interactive_approval_presents_mutable_nested_payload() -> None:
    from loushang.coding.policy import InteractiveApprovalResolver
    from loushang.harness.approval import (
        ApprovalRequest,
        HeadlessApprovalResolver,
    )

    presented = asyncio.Event()
    payloads: list[dict[str, object]] = []
    resolver = InteractiveApprovalResolver(
        fallback=HeadlessApprovalResolver(mode="deny")
    )

    def presenter(payload: dict[str, object]) -> None:
        payloads.append(payload)
        presented.set()

    resolver.set_request_presenter(presenter)

    async def run() -> None:
        pending = asyncio.create_task(
            resolver.resolve(
                ApprovalRequest(
                    tool_name="edit",
                    arguments={"edits": [{"oldText": "before", "newText": "after"}]},
                )
            )
        )
        await presented.wait()
        action_id = payloads[0]["action_id"]
        assert isinstance(action_id, str)
        assert await resolver.handle_result(action_id, approved=True)
        await pending

    asyncio.run(run())

    arguments = payloads[0]["arguments"]
    assert arguments == {"edits": [{"oldText": "before", "newText": "after"}]}
    assert isinstance(arguments, dict)
    assert isinstance(arguments["edits"], list)


def test_coding_resolve_approval_uses_harness_result_validation() -> None:
    import pytest

    from loushang.coding.policy import ApprovalRequest, resolve_approval

    class InvalidResolver:
        def resolve(self, request):
            del request
            return "allow"

    with pytest.raises(TypeError, match="ApprovalResolver returned str"):
        asyncio.run(
            resolve_approval(
                InvalidResolver(), ApprovalRequest(tool_name="write", arguments={})
            )
        )


def test_coding_interactive_approval_rejects_rebind_without_retaining_callback() -> (
    None
):
    import pytest

    from loushang.coding.policy import (
        HeadlessApprovalResolver,
        InteractiveApprovalResolver,
    )

    resolver = InteractiveApprovalResolver(
        fallback=HeadlessApprovalResolver(mode="deny")
    )
    resolver.dispose()

    def presenter(payload: dict[str, object]) -> None:
        del payload

    with pytest.raises(RuntimeError, match="disposed"):
        resolver.set_request_presenter(presenter)

    assert resolver._request_presenter is None
