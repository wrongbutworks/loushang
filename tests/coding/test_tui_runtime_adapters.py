from __future__ import annotations

from types import SimpleNamespace

from loushang.coding.presentation.tui.runtime import (
    pending_followups_reader,
    pending_steers_reader,
    session_keybindings,
    tool_definition_resolver,
)


def test_tool_definition_resolver_supports_standard_sessions() -> None:
    def snake_case(name: str) -> str:
        return f"snake:{name}"

    snake_resolver = tool_definition_resolver(
        SimpleNamespace(get_tool_definition=snake_case)
    )

    assert snake_resolver is not None
    assert snake_resolver("write") == "snake:write"


def test_pending_steers_reader_keeps_only_string_messages() -> None:
    session = SimpleNamespace(
        get_steering_messages=lambda: ["first", 7, None, "last"]
    )

    assert pending_steers_reader(session)() == ("first", "last")


def test_pending_followups_reader_is_fail_soft() -> None:
    def broken_reader() -> tuple[str, ...]:
        raise RuntimeError("queue unavailable")

    session = SimpleNamespace(get_follow_up_messages=broken_reader)

    assert pending_followups_reader(session)() == ()


def test_session_keybindings_falls_back_to_settings_snapshot() -> None:
    bindings = {"tui.input.submit": ("enter", "ctrl+j")}
    settings_manager = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(keybindings=bindings)
    )
    session = SimpleNamespace(settings_manager=settings_manager)

    assert session_keybindings(session) is bindings
