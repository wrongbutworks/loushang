from __future__ import annotations

import loushang.method as method


def test_method_public_api_exports_p1_types_only() -> None:
    expected = {
        "MethodContext",
        "MethodDescriptor",
        "MethodPlan",
        "MethodProjection",
        "MethodStep",
    }

    for name in expected:
        assert hasattr(method, name)

    assert not hasattr(method, "TaskFlow")
    assert not hasattr(method, "AgentLane")
    assert not hasattr(method, "CollaborationBus")
