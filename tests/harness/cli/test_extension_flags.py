from __future__ import annotations

from loushang.harness.cli import (
    apply_extension_flag_values,
    collect_extension_flags,
)


class _Runner:
    def __init__(self) -> None:
        self.values: dict[str, bool | str] = {}

    def get_flags(self):
        return [type("Flag", (), {"name": "plan"})(), type("Flag", (), {})()]

    def set_flag_value(self, name: str, value: bool | str) -> None:
        self.values[name] = value


def test_extension_flag_runtime_collects_named_flags_and_applies_values() -> None:
    session = type("Session", (), {"extension_runner": _Runner()})()

    flags = collect_extension_flags(session)
    apply_extension_flag_values(session, {"plan": True})

    assert tuple(flags) == ("plan",)
    assert session.extension_runner.values == {"plan": True}


def test_extension_flag_runtime_is_best_effort_for_missing_runner() -> None:
    assert collect_extension_flags(object()) == {}
    apply_extension_flag_values(object(), {"plan": True})
