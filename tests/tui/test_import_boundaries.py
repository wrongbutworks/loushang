from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path


def test_import_loushang_tui_does_not_import_legacy_rendering_libraries() -> None:
    _drop_modules_with_prefix("loushang.tui")
    for module_name in ("prompt_toolkit", "rich", "pygments"):
        sys.modules.pop(module_name, None)

    tui_module = importlib.import_module("loushang.tui")

    assert "prompt_toolkit" not in sys.modules
    assert "rich" not in sys.modules
    assert "pygments" not in sys.modules
    assert tui_module.MarkdownRenderer.__module__ == "loushang.tui.markdown.renderer"

    content_module = importlib.import_module("loushang.tui.content")
    markdown_module = importlib.import_module("loushang.tui.markdown")
    assert content_module.MarkdownRenderer is tui_module.MarkdownRenderer
    assert markdown_module.MarkdownRenderer is tui_module.MarkdownRenderer
    assert "rich" not in sys.modules
    assert "pygments" not in sys.modules


def test_import_loushang_tui_without_posix_terminal_modules() -> None:
    result = _run_python_without_posix_terminal_modules(
        """
import loushang.tui

print(loushang.tui.TerminalInputMode.__name__)
"""
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "TerminalInputMode"


def test_terminal_input_mode_is_noop_without_posix_terminal_modules() -> None:
    result = _run_python_without_posix_terminal_modules(
        """
from io import StringIO

from loushang.tui.terminal_input import TerminalInputMode


class TtyInput:
    def fileno(self):
        return 42

    def isatty(self):
        return True


stdout = StringIO()
with TerminalInputMode(stdin=TtyInput(), stdout=stdout):
    pass

print(repr(stdout.getvalue()))
"""
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "''"


def test_pyproject_declares_markdown_it_py_as_direct_dependency() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.lower().startswith("markdown-it-py") for dependency in dependencies)


def test_pyproject_does_not_declare_legacy_tui_dependencies() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    normalized_dependencies = tuple(dependency.lower() for dependency in dependencies)

    assert not any(dependency.startswith("prompt-toolkit") for dependency in normalized_dependencies)
    assert not any(dependency.startswith("rich") for dependency in normalized_dependencies)


def _drop_modules_with_prefix(prefix: str) -> None:
    for module_name in tuple(sys.modules):
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            sys.modules.pop(module_name, None)


def _run_python_without_posix_terminal_modules(script: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_path = str(Path.cwd() / "src")
    env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    block_posix_modules = """
import importlib.abc
import sys


class BlockPosixTerminalModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"termios", "tty"}:
            raise ModuleNotFoundError(f"No module named {fullname!r}")
        return None


sys.meta_path.insert(0, BlockPosixTerminalModules())
"""
    return subprocess.run(
        [sys.executable, "-c", f"{block_posix_modules}\n{script}"],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
