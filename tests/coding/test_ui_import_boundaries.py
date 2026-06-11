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

importlib.import_module("loushang.coding.ui.native_state")

assert "loushang.coding.ui.mode" not in sys.modules
assert "loushang.coding.ui.renderer" not in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


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
