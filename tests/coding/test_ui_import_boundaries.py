from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_importing_coding_ui_state_does_not_load_tui_mode_entrypoint() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib
import sys

importlib.import_module("loushang.coding.ui.screen_state")

assert "loushang.coding.ui.mode" not in sys.modules
assert "loushang.coding.ui.plain_renderer" not in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


def test_old_coding_ui_renderer_module_is_removed() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib

try:
    importlib.import_module("loushang.coding.ui.renderer")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("loushang.coding.ui.renderer should be named plain_renderer")
"""
    )

    assert result.returncode == 0, result.stderr


def test_old_coding_ui_events_module_is_removed() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib

try:
    importlib.import_module("loushang.coding.ui.events")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("loushang.coding.ui.events should be named plain_events")
"""
    )

    assert result.returncode == 0, result.stderr


def test_old_coding_ui_app_module_is_removed() -> None:
    result = _run_python_import_boundary_check(
        """
import importlib

try:
    importlib.import_module("loushang.coding.ui.app")
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("loushang.coding.ui.app should be named plain_app")
"""
    )

    assert result.returncode == 0, result.stderr


def test_coding_ui_does_not_depend_on_legacy_settings_list_primitives() -> None:
    forbidden = (
        "SettingItem",
        "SettingsList",
        "SettingsListRenderer",
        "SettingsSurface",
        "legacy_settings",
    )
    offenders: list[str] = []
    for path in Path("src/loushang/coding/ui").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")

    assert offenders == []


def test_active_coding_ui_surfaces_do_not_use_legacy_native_product_names() -> None:
    forbidden = (
        "NativeCoding",
        "NativeSurface",
        "NativeInput",
        "Native TUI",
        "native coding TUI",
        "native event projection",
        "native/session event",
        "native terminal TUI",
        "current native TUI",
        "native `tui`",
        "native TUI runner",
        "native TUI 已",
        "native TUI 中",
        "native TUI 属于",
        "native TUI 是",
        "src/loushang/coding/ui/native_",
        "tests/coding/test_native_coding_tui",
        "native_app",
        "native_events",
        "native_input",
        "native_loop",
        "native_state",
        "native_surfaces",
        "native_tui",
        "test_native_tui",
    )
    offenders: list[str] = []
    roots = (
        Path("src/loushang/coding/ui"),
        Path("tests/coding"),
        Path("docs/internals/architecture/coding"),
        Path("docs/internals/testing"),
    )
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md"}:
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if "archive" in path.parts or "history" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path}:{token}")

    assert offenders == []


def _run_python_import_boundary_check(script: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path.cwd() / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
