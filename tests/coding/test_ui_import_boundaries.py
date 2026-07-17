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


def test_conversation_raw_event_dispatch_stays_in_coding_adapter() -> None:
    adapter = Path(
        "src/loushang/coding/ui/conversation_event_adapter.py"
    ).read_text(encoding="utf-8")
    assert 'event.get("type")' in adapter

    for path in (
        Path("src/loushang/coding/ui/plain_events.py"),
        Path("src/loushang/coding/ui/screen_events.py"),
    ):
        assert 'event.get("type")' not in path.read_text(encoding="utf-8")


def test_shared_interaction_types_are_not_redefined_in_coding_ui() -> None:
    moved_definitions = {
        Path("src/loushang/coding/ui/model_list.py"): ("class ModelChoice",),
        Path("src/loushang/coding/ui/settings_common.py"): ("class ConfigRow",),
        Path("src/loushang/coding/ui/settings_config.py"): (
            "class ConfigSettingsPage",
        ),
        Path("src/loushang/coding/ui/settings_page.py"): (
            "class ModelPage",
            "class StaticLinesPage",
        ),
        Path("src/loushang/coding/ui/settings_status_line.py"): (
            "class StatusLineSettingsPage",
        ),
        Path("src/loushang/coding/ui/plain_toolbar.py"): (
            "class PlainToolbarSnapshot",
            "def render_plain_toolbar",
        ),
        Path("src/loushang/coding/ui/status_provider.py"): (
            "class CodingTuiStatusProvider",
            "class StatusSnapshot",
        ),
        Path("src/loushang/coding/ui/transcript_source.py"): (
            "def _recent_assistant_texts",
            "def _merge_active_window_records",
            "def _decorated_suffix_prefix_overlap",
            "def _history_projected_record",
        ),
        Path("src/loushang/coding/ui/screen_surfaces.py"): (
            "class ModelSelectorSurface",
            "class ScreenSurfaceView",
        ),
    }

    offenders = [
        f"{path}:{definition}"
        for path, definitions in moved_definitions.items()
        for definition in definitions
        if definition in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_shared_status_provider_does_not_own_settings_manager_adaptation() -> None:
    source = Path("src/loushang/harnesstui/status/provider.py").read_text(
        encoding="utf-8"
    )

    assert "settings_manager" not in source
    assert "status_line_settings_from_control" not in source
    assert "status_line_settings_to_patch" not in source


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
