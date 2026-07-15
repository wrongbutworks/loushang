from loushang.ai.auth import AuthResolution


def test_auth_resolution_represents_satisfied_and_missing_auth() -> None:
    satisfied = AuthResolution(
        provider="example",
        model_id="example-1",
        endpoint_id="responses",
        auth_required=True,
        satisfied=True,
        source="env",
        headers={"Authorization": "Bearer secret"},
    )
    missing = AuthResolution(
        provider="example",
        model_id="example-1",
        endpoint_id="responses",
        auth_required=True,
        satisfied=False,
    )

    assert satisfied.headers == {"Authorization": "Bearer secret"}
    assert missing.headers == {}


def test_coding_auth_resolution_is_the_ai_value_object() -> None:
    from loushang.coding.control import AuthResolution as CodingAuthResolution

    assert CodingAuthResolution is AuthResolution
