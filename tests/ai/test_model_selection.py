import pytest

from loushang.ai import ModelSelection


def test_model_selection_identifies_an_optional_endpoint() -> None:
    assert ModelSelection(
        provider="example",
        model_id="example-1",
        endpoint_id="responses",
    ) == ModelSelection(
        provider="example",
        model_id="example-1",
        endpoint_id="responses",
    )
    assert ModelSelection(provider="example", model_id="example-1").endpoint_id is None


@pytest.mark.skip(reason="coding auth integration is pending its dedicated rebuild")
def test_coding_model_selection_is_the_ai_value_object() -> None:
    from loushang.ai.model import ModelSelection as CodingModelSelection

    assert CodingModelSelection is ModelSelection
