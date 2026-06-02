from __future__ import annotations

from types import SimpleNamespace

from loushang.tui import terminal_platform
from loushang.tui.terminal_platform import DefaultTerminalPlatformAdapter

ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def test_windows_console_input_mode_disables_quick_edit_and_enables_vt(monkeypatch) -> None:
    initial_mode = ENABLE_QUICK_EDIT_MODE | 0x0004
    kernel32 = _FakeKernel32(initial_mode=initial_mode)
    monkeypatch.setattr(terminal_platform.sys, "platform", "win32")
    monkeypatch.setattr(terminal_platform.ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)

    adapter = DefaultTerminalPlatformAdapter()

    assert adapter.enable_windows_vt_input(object()) is True

    expected_mode = (initial_mode | ENABLE_EXTENDED_FLAGS | ENABLE_VIRTUAL_TERMINAL_INPUT) & ~ENABLE_QUICK_EDIT_MODE
    assert kernel32.set_modes == [expected_mode]
    assert adapter.windows_console_mode_configured() is True
    assert adapter.windows_vt_input_active() is True

    adapter.disable_windows_vt_input()

    assert kernel32.set_modes == [expected_mode, initial_mode]
    assert adapter.windows_console_mode_configured() is False
    assert adapter.windows_vt_input_active() is False


def test_windows_console_input_mode_disables_quick_edit_when_vt_input_is_rejected(monkeypatch) -> None:
    initial_mode = ENABLE_QUICK_EDIT_MODE | 0x0004
    kernel32 = _FakeKernel32(initial_mode=initial_mode, reject_vt_input=True)
    monkeypatch.setattr(terminal_platform.sys, "platform", "win32")
    monkeypatch.setattr(terminal_platform.ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)

    adapter = DefaultTerminalPlatformAdapter()

    assert adapter.enable_windows_vt_input(object()) is False

    vt_mode = (initial_mode | ENABLE_EXTENDED_FLAGS | ENABLE_VIRTUAL_TERMINAL_INPUT) & ~ENABLE_QUICK_EDIT_MODE
    quick_edit_mode = (initial_mode | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE
    assert kernel32.set_modes == [vt_mode, quick_edit_mode]
    assert adapter.windows_console_mode_configured() is True
    assert adapter.windows_vt_input_active() is False

    adapter.disable_windows_vt_input()

    assert kernel32.set_modes == [vt_mode, quick_edit_mode, initial_mode]
    assert adapter.windows_console_mode_configured() is False


def test_windows_console_output_mode_enables_vt_processing_and_restores(monkeypatch) -> None:
    initial_mode = 0x0002
    kernel32 = _FakeKernel32(initial_mode=initial_mode)
    monkeypatch.setattr(terminal_platform.sys, "platform", "win32")
    monkeypatch.setattr(terminal_platform.ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False)

    adapter = DefaultTerminalPlatformAdapter()

    assert adapter.enable_windows_vt_output(object()) is True

    expected_mode = initial_mode | ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
    assert kernel32.set_modes == [expected_mode]
    assert adapter.windows_vt_output_active() is True

    adapter.disable_windows_vt_output()

    assert kernel32.set_modes == [expected_mode, initial_mode]
    assert adapter.windows_vt_output_active() is False


class _FakeKernel32:
    def __init__(self, *, initial_mode: int, reject_vt_input: bool = False) -> None:
        self.initial_mode = initial_mode
        self.reject_vt_input = reject_vt_input
        self.set_modes: list[int] = []

    def GetStdHandle(self, _handle_id: int) -> int:
        return 123

    def GetConsoleMode(self, _handle: object, mode_ptr: object) -> int:
        mode_ptr._obj.value = self.initial_mode
        return 1

    def SetConsoleMode(self, _handle: object, mode: object) -> int:
        value = int(getattr(mode, "value", mode))
        self.set_modes.append(value)
        if self.reject_vt_input and value & ENABLE_VIRTUAL_TERMINAL_INPUT:
            return 0
        return 1
