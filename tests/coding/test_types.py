from __future__ import annotations


def test_coding_types_exports_model_selection_without_control_config_shim() -> None:
    import loushang.coding.types as coding_types

    assert coding_types.__all__ == ["ModelSelection"]
    assert coding_types.ModelSelection(provider="faux", model_id="alpha").endpoint_id is None
    assert not hasattr(coding_types, "ControlConfig")
