"""Harness model-data binding for terminal selection models."""

from __future__ import annotations

from collections.abc import Iterable

from loushang.harness.session.model_selection import (
    model_choice_data_from_details,
    model_identity_data,
)
from loushang.harnesstui.selection.catalog import ModelChoice, ModelChoiceIdentity


def model_identity_from_value(selection: object | None) -> ModelChoiceIdentity:
    data = model_identity_data(selection)
    return ModelChoiceIdentity(label=data.label, value=data.value)


def model_choices_from_details(details: Iterable[object]) -> list[ModelChoice]:
    return [
        ModelChoice(
            label=data.label,
            value=data.value,
            selection=data.selection,
            endpoint_id=data.endpoint_id,
            region=data.region,
            lane=data.lane,
            api=data.api,
            preferred_endpoint=data.preferred_endpoint,
            description=data.description,
        )
        for data in model_choice_data_from_details(details)
    ]


__all__ = ["model_choices_from_details", "model_identity_from_value"]
