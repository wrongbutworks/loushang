from __future__ import annotations


def test_model_selection_is_owned_by_ai() -> None:
    import loushang.ai.model as ai_model

    assert (
        ai_model.ModelSelection(provider="faux", model_id="alpha").endpoint_id is None
    )
    assert not hasattr(ai_model, "ControlConfig")
