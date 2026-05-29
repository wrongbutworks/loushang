from __future__ import annotations

import ctypes
import sys
from typing import Protocol

APPLE_TERMINAL_SHIFT_ENTER_SEQUENCE = "\x1b[13;2u"
_APPLE_EVENT_SOURCE_STATE_COMBINED_SESSION = 0
_APPLE_EVENT_FLAG_MASK_SHIFT = 1 << 17
_ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
_STD_INPUT_HANDLE = -10


class TerminalPlatformAdapter(Protocol):
    def enable_windows_vt_input(self, stdin: object) -> bool: ...

    def disable_windows_vt_input(self) -> None: ...

    def apple_shift_pressed(self) -> bool: ...


class DefaultTerminalPlatformAdapter:
    def __init__(self) -> None:
        self._windows_handle: int | None = None
        self._windows_original_mode: int | None = None

    def enable_windows_vt_input(self, stdin: object) -> bool:
        if sys.platform != "win32":
            return False
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = ctypes.c_void_p(_windows_stdin_handle(stdin, kernel32))
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            requested = ctypes.c_uint32(mode.value | _ENABLE_VIRTUAL_TERMINAL_INPUT)
            if not kernel32.SetConsoleMode(handle, requested):
                return False
        except Exception:  # noqa: BLE001
            return False
        self._windows_handle = handle.value
        self._windows_original_mode = int(mode.value)
        return self._windows_handle is not None

    def disable_windows_vt_input(self) -> None:
        if sys.platform != "win32" or self._windows_handle is None or self._windows_original_mode is None:
            return
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.SetConsoleMode(ctypes.c_void_p(self._windows_handle), ctypes.c_uint32(self._windows_original_mode))
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._windows_handle = None
            self._windows_original_mode = None

    def apple_shift_pressed(self) -> bool:
        if sys.platform != "darwin":
            return False
        if _apple_shift_pressed_via_quartz():
            return True
        try:
            from loushang.tui.native_modifiers import is_shift_pressed
        except Exception:  # noqa: BLE001
            return False
        try:
            return bool(is_shift_pressed())
        except Exception:  # noqa: BLE001
            return False


def _windows_stdin_handle(stdin: object, kernel32: object) -> int:
    fileno = getattr(stdin, "fileno", None)
    if callable(fileno):
        try:
            import msvcrt

            return int(msvcrt.get_osfhandle(fileno()))
        except Exception:  # noqa: BLE001
            pass
    return int(kernel32.GetStdHandle(_STD_INPUT_HANDLE))


def _apple_shift_pressed_via_quartz() -> bool:
    try:
        application_services = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        flags_state = application_services.CGEventSourceFlagsState
        flags_state.argtypes = [ctypes.c_uint32]
        flags_state.restype = ctypes.c_uint64
        flags = int(flags_state(_APPLE_EVENT_SOURCE_STATE_COMBINED_SESSION))
    except Exception:  # noqa: BLE001
        return False
    return bool(flags & _APPLE_EVENT_FLAG_MASK_SHIFT)


__all__ = [
    "APPLE_TERMINAL_SHIFT_ENTER_SEQUENCE",
    "DefaultTerminalPlatformAdapter",
    "TerminalPlatformAdapter",
]
