from __future__ import annotations

import importlib

import loushang.protocol as protocol


def test_protocol_public_surface_is_frozen_for_compatibility() -> None:
    assert set(protocol.__all__) == {
        "JSONPrimitive",
        "JSONValue",
        "JsonValueError",
        "dump_json_value",
        "require_json_mapping",
        "require_json_value",
    }
    assert all(hasattr(protocol, name) for name in protocol.__all__)


def test_protocol_json_value_submodule_remains_importable() -> None:
    module = importlib.import_module("loushang.protocol.json_value")

    assert module.__name__ == "loushang.protocol.json_value"
