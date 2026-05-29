from __future__ import annotations

from loushang.tui.input import InputEvent
from loushang.tui.keyboard_protocol import KeyboardProtocolController


def test_keyboard_protocol_startup_queries_kitty_first() -> None:
    controller = KeyboardProtocolController(strategy="kitty_then_modify_other_keys", fallback_delay_ms=150)

    assert controller.startup_sequences(now_ms=1_000) == ("\x1b[?u",)
    assert not controller.kitty_active
    assert not controller.modify_other_keys_active


def test_keyboard_protocol_response_enables_kitty_flags() -> None:
    controller = KeyboardProtocolController(strategy="kitty_then_modify_other_keys")
    controller.startup_sequences(now_ms=0)

    writes = controller.consume_control_event(InputEvent(kind="signal", signal="kitty_protocol", text="7"))

    assert writes == ("\x1b[>7u",)
    assert controller.kitty_active
    assert not controller.modify_other_keys_active
    assert controller.fallback_sequences_if_due(now_ms=10_000) == ()


def test_keyboard_protocol_falls_back_to_modify_other_keys_after_deadline() -> None:
    controller = KeyboardProtocolController(strategy="kitty_then_modify_other_keys", fallback_delay_ms=150)
    controller.startup_sequences(now_ms=1_000)

    assert controller.fallback_sequences_if_due(now_ms=1_149) == ()
    assert controller.fallback_sequences_if_due(now_ms=1_150) == ("\x1b[>4;2m",)
    assert controller.modify_other_keys_active
    assert controller.fallback_sequences_if_due(now_ms=2_000) == ()


def test_keyboard_protocol_modify_other_keys_strategy_starts_immediately() -> None:
    controller = KeyboardProtocolController(strategy="modify_other_keys")

    assert controller.startup_sequences(now_ms=0) == ("\x1b[>4;2m",)
    assert controller.modify_other_keys_active


def test_keyboard_protocol_shutdown_disables_only_enabled_modes_and_is_idempotent() -> None:
    controller = KeyboardProtocolController(strategy="kitty_then_modify_other_keys", fallback_delay_ms=150)
    controller.startup_sequences(now_ms=0)
    controller.consume_control_event(InputEvent(kind="signal", signal="kitty_protocol", text="7"))

    assert controller.shutdown_sequences() == ("\x1b[<u",)
    assert controller.shutdown_sequences() == ()

    fallback = KeyboardProtocolController(strategy="kitty_then_modify_other_keys", fallback_delay_ms=150)
    fallback.startup_sequences(now_ms=0)
    fallback.fallback_sequences_if_due(now_ms=150)

    assert fallback.shutdown_sequences() == ("\x1b[>4;0m",)
    assert fallback.shutdown_sequences() == ()


def test_keyboard_protocol_ignores_unrelated_control_events() -> None:
    controller = KeyboardProtocolController(strategy="kitty_then_modify_other_keys")
    controller.startup_sequences(now_ms=0)

    assert controller.consume_control_event(InputEvent(kind="signal", signal="cell_size", text="18;9")) == ()
    assert not controller.kitty_active
