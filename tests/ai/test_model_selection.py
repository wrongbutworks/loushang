import pytest

from loushang.ai import ModelSelection
from loushang.ai.model import parse_model_selection_reference


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


@pytest.mark.parametrize(
    ("model", "provider", "expected"),
    [
        (
            "provider/model",
            None,
            ModelSelection(provider="provider", model_id="model"),
        ),
        (
            "provider:endpoint:model",
            None,
            ModelSelection(
                provider="provider", endpoint_id="endpoint", model_id="model"
            ),
        ),
        (
            "model",
            "provider",
            ModelSelection(provider="provider", model_id="model"),
        ),
    ],
)
def test_model_selection_reference_parser_accepts_shared_forms(
    model: str,
    provider: str | None,
    expected: ModelSelection,
) -> None:
    assert parse_model_selection_reference(model, provider=provider) == expected


def test_model_selection_reference_parser_rejects_partial_reference() -> None:
    with pytest.raises(ValueError, match="Model selection requires"):
        parse_model_selection_reference("model")


@pytest.mark.skip(reason="coding auth integration is pending its dedicated rebuild")
def test_coding_model_selection_is_the_ai_value_object() -> None:
    from loushang.ai.model import ModelSelection as CodingModelSelection

    assert CodingModelSelection is ModelSelection
