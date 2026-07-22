from __future__ import annotations

from loushang.ai.model import Model, ModelSelection
from loushang.harness.session.model_resolution import (
    classify_model_resolution_failure,
    resolve_default_model,
    scoped_models_from_patterns,
)


def _model() -> Model:
    return Model(
        id="chat",
        provider="provider",
        endpoint="primary",
    )


def test_resolve_default_model_reports_failure_through_product_callback() -> None:
    selection = ModelSelection(provider="provider", model_id="missing")
    failures: list[tuple[ModelSelection, str]] = []

    result = resolve_default_model(
        selection,
        build_model=lambda _: (_ for _ in ()).throw(KeyError("missing")),
        on_unavailable=lambda selected, _error, reason: failures.append(
            (selected, reason)
        ),
    )

    assert result.model is None
    assert result.reason == "missing"
    assert failures == [(selection, "missing")]


def test_resolve_default_model_keeps_successful_model() -> None:
    model = _model()
    result = resolve_default_model(
        ModelSelection(provider="provider", model_id="chat"),
        build_model=lambda _: model,
    )

    assert result.model is model
    assert result.error is None


def test_classify_explicit_endpoint_failure_is_stable() -> None:
    selection = ModelSelection(
        provider="provider", endpoint_id="missing", model_id="chat"
    )

    assert (
        classify_model_resolution_failure(
            selection,
            error=KeyError("missing"),
            endpoint_lookup=lambda _provider, _endpoint: None,
        )
        == "endpoint_unavailable"
    )


def test_scoped_models_from_patterns_is_product_neutral() -> None:
    selections = {
        "provider/chat": ModelSelection(
            provider="provider", endpoint_id="primary", model_id="chat"
        )
    }

    assert scoped_models_from_patterns(
        ("provider/chat:high", "missing"),
        resolve_model=selections.get,
    ) == [
        {
            "model": {
                "provider": "provider",
                "endpoint_id": "primary",
                "model_id": "chat",
            },
            "thinkingLevel": "high",
        }
    ]
