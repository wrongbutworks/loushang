from __future__ import annotations

import importlib

import loushang.foundation.json as foundation_json
import loushang.protocol as protocol


def test_foundation_json_is_the_canonical_public_surface() -> None:
    assert set(foundation_json.__all__) == {
        "JSONPrimitive",
        "JSONValue",
        "JsonValueError",
        "dump_json_value",
        "require_json_mapping",
        "require_json_value",
    }
    assert foundation_json.require_json_value({"ok": [True]}) == {"ok": [True]}


def test_protocol_root_forwards_canonical_json_symbols() -> None:
    for name in foundation_json.__all__:
        assert getattr(protocol, name) is getattr(foundation_json, name)


def test_protocol_json_value_module_forwards_canonical_json_symbols() -> None:
    compatibility_module = importlib.import_module("loushang.protocol.json_value")

    for name in foundation_json.__all__:
        assert getattr(compatibility_module, name) is getattr(foundation_json, name)
