from __future__ import annotations

from dataclasses import dataclass

from loushang.tui.input import InputEvent
from loushang.tui.terminal_capabilities import KeyboardProtocolStrategy

KITTY_QUERY_SEQUENCE = "\x1b[?u"
KITTY_ENABLE_FLAGS_SEQUENCE = "\x1b[>7u"
KITTY_DISABLE_SEQUENCE = "\x1b[<u"
MODIFY_OTHER_KEYS_ENABLE_SEQUENCE = "\x1b[>4;2m"
MODIFY_OTHER_KEYS_DISABLE_SEQUENCE = "\x1b[>4;0m"


@dataclass(slots=True)
class KeyboardProtocolController:
    strategy: KeyboardProtocolStrategy = "kitty_then_modify_other_keys"
    fallback_delay_ms: int = 150
    kitty_active: bool = False
    modify_other_keys_active: bool = False
    _kitty_query_sent: bool = False
    _kitty_enable_sent: bool = False
    _startup_ms: int | None = None
    _fallback_attempted: bool = False

    def startup_sequences(self, *, now_ms: int) -> tuple[str, ...]:
        if self.strategy == "legacy":
            return ()
        self._startup_ms = now_ms
        if self.strategy == "modify_other_keys":
            return self._enable_modify_other_keys()
        self._kitty_query_sent = True
        return (KITTY_QUERY_SEQUENCE,)

    def consume_control_event(self, event: InputEvent) -> tuple[str, ...]:
        if event.kind != "signal" or event.signal != "kitty_protocol":
            return ()
        if self.strategy != "kitty_then_modify_other_keys" or not self._kitty_query_sent:
            return ()
        if self.kitty_active or self.modify_other_keys_active:
            return ()
        self.kitty_active = True
        self._kitty_enable_sent = True
        return (KITTY_ENABLE_FLAGS_SEQUENCE,)

    def consume_control_events(self, events: tuple[InputEvent, ...]) -> tuple[str, ...]:
        writes: list[str] = []
        for event in events:
            writes.extend(self.consume_control_event(event))
        return tuple(writes)

    def fallback_sequences_if_due(self, *, now_ms: int) -> tuple[str, ...]:
        if self.strategy != "kitty_then_modify_other_keys":
            return ()
        if self.kitty_active or self.modify_other_keys_active or self._fallback_attempted:
            return ()
        if self._startup_ms is None or now_ms < self._startup_ms + self.fallback_delay_ms:
            return ()
        self._fallback_attempted = True
        return self._enable_modify_other_keys()

    def next_fallback_delay_ms(self, *, now_ms: int) -> int | None:
        if self.strategy != "kitty_then_modify_other_keys":
            return None
        if self.kitty_active or self.modify_other_keys_active or self._fallback_attempted:
            return None
        if self._startup_ms is None:
            return None
        return max(0, self._startup_ms + self.fallback_delay_ms - now_ms)

    def shutdown_sequences(self) -> tuple[str, ...]:
        writes: list[str] = []
        if self.kitty_active:
            writes.append(KITTY_DISABLE_SEQUENCE)
            self.kitty_active = False
        if self.modify_other_keys_active:
            writes.append(MODIFY_OTHER_KEYS_DISABLE_SEQUENCE)
            self.modify_other_keys_active = False
        return tuple(writes)

    def _enable_modify_other_keys(self) -> tuple[str, ...]:
        if self.modify_other_keys_active:
            return ()
        self.modify_other_keys_active = True
        return (MODIFY_OTHER_KEYS_ENABLE_SEQUENCE,)


__all__ = [
    "KITTY_DISABLE_SEQUENCE",
    "KITTY_ENABLE_FLAGS_SEQUENCE",
    "KITTY_QUERY_SEQUENCE",
    "MODIFY_OTHER_KEYS_DISABLE_SEQUENCE",
    "MODIFY_OTHER_KEYS_ENABLE_SEQUENCE",
    "KeyboardProtocolController",
]
